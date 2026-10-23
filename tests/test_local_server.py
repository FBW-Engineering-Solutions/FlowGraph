"""Real HTTP and subprocess tests for the experimental local API."""

from __future__ import annotations

import json
import threading
import time
from http.client import HTTPConnection
from urllib.parse import urlencode

import pytest

from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import WorkflowEdge, WorkflowGraph
from flowgraph.application.workflow_io import workflow_to_dict
from flowgraph.core_cli import build_parser
from flowgraph.server.http import LocalServer
from flowgraph.server.jobs import JobManager
from flowgraph.server.workspace import Workspace


@pytest.fixture
def api(tmp_path):
    server = LocalServer(tmp_path, port=0, execution_timeout=15)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def request(api, method, path, body=None, headers=None):
    connection = HTTPConnection("127.0.0.1", api.server_port, timeout=20)
    supplied = {"Authorization": f"Bearer {api.token}"}
    if isinstance(body, dict):
        body = json.dumps(body).encode()
        supplied["Content-Type"] = "application/json"
    supplied.update(headers or {})
    try:
        connection.request(method, path, body=body, headers=supplied)
        response = connection.getresponse()
        content = response.read()
        value = (
            json.loads(content)
            if response.getheader("Content-Type").startswith("application/json")
            else content
        )
        return response.status, value
    finally:
        connection.close()


def workflow(code=None):
    registry = create_node_registry()
    if code is not None:
        graph = WorkflowGraph(
            [registry.create_instance("user-function", "python", parameters={"code": code})]
        )
    else:
        graph = WorkflowGraph(
            [
                registry.create_instance("set-string", "source", parameters={"value": "hello"}),
                registry.create_instance(
                    "workflow-output", "output", parameters={"name": "result"}
                ),
            ]
        )
        graph.add_edge(WorkflowEdge("source", "value", "output", "value"), registry)
        graph.sync_boundary_nodes(registry)
    return workflow_to_dict(graph)


def wait_job(api, identifier):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        status, job = request(api, "GET", f"/api/v1/executions/{identifier}")
        assert status == 200
        if job["state"] != "running":
            return job
        time.sleep(0.02)
    pytest.fail("Execution did not finish")


def test_runtime_catalog_and_authentication(api):
    status, runtime = request(api, "GET", "/api/v1/runtime")
    assert status == 200
    assert runtime["version"] == 1
    assert runtime["kind"] == "native"
    assert runtime["workflow_format_version"] == 3
    assert runtime["capabilities"]["mountDirectory"] is False
    assert "numpy" in runtime["packages"]
    assert runtime["versions"]["Python"]
    status, catalog = request(api, "GET", "/api/v1/catalog")
    assert status == 200
    assert catalog["format"] == "flowgraph-web-node-catalog"
    assert (
        request(api, "GET", "/api/v1/runtime", headers={"Authorization": "Bearer wrong"})[0] == 401
    )
    assert request(api, "GET", "/api/v1/runtime", headers={"Host": "evil.example"})[0] == 403
    assert (
        request(api, "GET", "/api/v1/runtime", headers={"Origin": "http://evil.example"})[0] == 403
    )
    assert (
        request(api, "GET", "/api/v1/runtime", headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
    )
    assert request(api, "GET", "/api/v1/runtime", headers={"Origin": api.origin})[0] == 200
    assert request(api, "GET", "/unknown")[0] == 404


def test_execution_and_invalid_workflow_recovery(api):
    status, job = request(api, "POST", "/api/v1/executions", {"workflow": workflow()})
    assert status == 202
    finished = wait_job(api, job["id"])
    assert finished["state"] == "completed"
    assert finished["result"]["outputs"] == {"result": "hello"}
    assert "display_inputs" in finished["result"]
    status, job = request(api, "POST", "/api/v1/executions", {"workflow": {}})
    assert status == 202
    finished = wait_job(api, job["id"])
    assert finished["state"] == "failed"
    assert finished["result"]["status"] == "error"
    status, job = request(api, "POST", "/api/v1/executions", {"workflow": workflow()})
    assert wait_job(api, job["id"])["state"] == "completed"
    assert request(api, "GET", "/api/v1/executions/missing")[0] == 404


def test_cancel_active_workflow_then_run_again(api):
    code = (
        "def Execute() -> tuple[int]:\n    import time\n    from pathlib import Path\n"
        "    Path('started').write_text('yes')\n    time.sleep(30)\n    return (1,)\n"
    )
    status, job = request(api, "POST", "/api/v1/executions", {"workflow": workflow(code)})
    assert status == 202
    assert request(api, "POST", "/api/v1/executions", {"workflow": workflow()})[0] == 409
    process = api.jobs.process
    deadline = time.monotonic() + 10
    while not (api.workspace.root / "started").exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert (api.workspace.root / "started").exists(), "Workflow never entered its long-running node"
    status, cancelled = request(api, "POST", f"/api/v1/executions/{job['id']}/cancel", b"")
    assert status == 200
    assert cancelled["state"] == "cancelled"
    assert process.poll() is not None
    status, following = request(api, "POST", "/api/v1/executions", {"workflow": workflow()})
    assert status == 202
    assert wait_job(api, following["id"])["state"] == "completed"


def test_execution_uses_workspace_as_working_directory(api):
    code = "def Execute() -> tuple[str]:\n    from pathlib import Path\n    Path('created.txt').write_text('native')\n    return ('done',)\n"
    status, job = request(api, "POST", "/api/v1/executions", {"workflow": workflow(code)})
    assert status == 202
    assert wait_job(api, job["id"])["state"] == "completed"
    assert (api.workspace.root / "created.txt").read_text() == "native"


def test_file_roundtrip_and_demos(api):
    route = "/api/v1/files/content?" + urlencode({"path": "nested/input.bin"})
    status, listing = request(api, "PUT", route, b"\x00\xffnative")
    assert status == 200
    assert listing["files"][0]["path"] == "nested/input.bin"
    assert listing["directories"] == ["nested"]
    assert request(api, "GET", route) == (200, b"\x00\xffnative")
    assert request(api, "GET", "/api/v1/files")[0] == 200
    assert request(api, "DELETE", route)[1]["files"] == []
    assert request(api, "GET", route)[0] == 404
    status, demos = request(api, "POST", "/api/v1/files/demo", b"")
    assert status == 200
    assert demos["copied"] == 5
    assert request(api, "POST", "/api/v1/files/demo", b"")[0] == 409


@pytest.mark.parametrize(
    "name", ["../escape", "/etc/passwd", "a/../../escape", "a\\escape", "a//b", "a/./b"]
)
def test_file_paths_cannot_escape_workspace(api, name):
    route = "/api/v1/files/content?" + urlencode({"path": name})
    assert request(api, "PUT", route, b"bad")[0] == 400


def test_symlinks_are_hidden_and_rejected(api, tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "secret").write_text("secret")
    link = tmp_path / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlinks unavailable")
    route = "/api/v1/files/content?" + urlencode({"path": "link/secret"})
    assert request(api, "GET", route)[0] == 400
    assert request(api, "PUT", route, b"bad")[0] == 400
    assert request(api, "GET", "/api/v1/files")[1]["files"] == []
    assert (outside / "secret").read_text() == "secret"


def test_request_validation_and_limits(api):
    assert request(api, "POST", "/api/v1/executions", b"{")[0] == 415
    assert (
        request(api, "POST", "/api/v1/executions", b"{", {"Content-Type": "application/json"})[0]
        == 400
    )
    assert request(api, "POST", "/api/v1/executions", {"workflow": "bad"})[0] == 400
    assert request(api, "GET", "/api/v1/files/content")[0] == 400
    api.max_request = 4
    assert request(api, "PUT", "/api/v1/files/content?path=large", b"12345")[0] == 413
    (api.workspace.root / "large").write_bytes(b"12345")
    assert request(api, "GET", "/api/v1/files/content?path=large")[0] == 400


def test_job_timeout_and_shutdown(tmp_path):
    manager = JobManager(tmp_path, timeout=0.01)
    job = manager.submit(workflow())
    for thread in manager.threads:
        thread.join(timeout=10)
    assert manager.get(job["id"])["state"] == "failed"
    assert "timeout" in manager.get(job["id"])["error"]
    manager.timeout = 30
    job = manager.submit(workflow())
    process = manager.process
    manager.close()
    assert process.poll() is not None
    assert manager.get(job["id"])["state"] == "cancelled"
    assert all(not thread.is_alive() for thread in manager.threads)
    with pytest.raises(RuntimeError, match="closed"):
        manager.submit(workflow())


def test_worker_crash_and_result_limit_are_reported(api):
    crash = "def Execute() -> tuple[int]:\n    import os\n    os._exit(7)\n    return (1,)\n"
    status, job = request(api, "POST", "/api/v1/executions", {"workflow": workflow(crash)})
    assert status == 202
    failed = wait_job(api, job["id"])
    assert failed["state"] == "failed"
    assert "without a result (7)" in failed["error"]
    api.jobs.max_result = 1
    status, job = request(api, "POST", "/api/v1/executions", {"workflow": workflow()})
    assert status == 202
    failed = wait_job(api, job["id"])
    assert failed["state"] == "failed"
    assert "size limit" in failed["error"]


def test_cli_and_configuration_validation(tmp_path):
    args = build_parser().parse_args(["serve", "--workspace", str(tmp_path), "--port", "0"])
    assert args.command == "serve"
    assert args.workspace == tmp_path
    with pytest.raises(ValueError):
        LocalServer(tmp_path, execution_timeout=float("nan"))
    with pytest.raises(ValueError):
        LocalServer(tmp_path, token="short")
    with pytest.raises(FileNotFoundError):
        Workspace(tmp_path / "missing")
