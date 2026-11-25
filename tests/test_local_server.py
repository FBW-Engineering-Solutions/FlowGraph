"""Real HTTP and subprocess tests for the experimental local API."""

from __future__ import annotations

import io
import json
import threading
import time
import zipfile
from http.client import HTTPConnection
from urllib.parse import urlencode

import pytest

from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import WorkflowEdge, WorkflowGraph
from flowgraph.application.workflow_io import workflow_to_dict
from flowgraph.core_cli import build_parser, main
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


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "null",
        "http://example.com",
        "http://127.0.0.1.evil.example:8082",
        "http://192.168.1.2:8082",
        "https://example.com/",
        "https://example.com/path",
        "https://user@example.com",
        "https://example.com\r\nInjected: yes",
    ],
)
def test_cors_rejects_invalid_origin_configuration(tmp_path, origin):
    with pytest.raises(ValueError):
        LocalServer(tmp_path, port=0, allowed_origins=(origin,))


@pytest.mark.parametrize(
    "origin",
    [
        "https://www.fbw-es.com",
        "http://127.0.0.1:8082",
        "http://localhost:8082",
        "http://[::1]:8082",
    ],
)
def test_cors_accepts_explicit_editor_origins(tmp_path, origin):
    with LocalServer(tmp_path, port=0, allowed_origins=(origin,)) as server:
        assert server.allowed_origins == frozenset({origin})


@pytest.mark.parametrize(
    "origin",
    [
        "https://www.fbw-es.com",
        "http://127.0.0.1:8082",
        "http://localhost:8082",
        "http://[::1]:8082",
    ],
)
def test_cors_is_opt_in_and_keeps_authentication(api, origin):
    assert request(api, "GET", "/api/v1/runtime", headers={"Origin": origin})[0] == 403
    api.allowed_origins = frozenset({origin})

    def exchange(method, path="/api/v1/runtime", **headers):
        connection = HTTPConnection("127.0.0.1", api.server_port, timeout=20)
        try:
            connection.request(
                method, path, headers={"Origin": origin, "Sec-Fetch-Site": "cross-site", **headers}
            )
            response = connection.getresponse()
            result = response.status, dict(response.getheaders()), response.read()
            return result
        finally:
            connection.close()

    status, headers, _ = exchange(
        "OPTIONS",
        **{
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "authorization, content-type",
            "Access-Control-Request-Private-Network": "true",
        },
    )
    assert status == 200
    assert headers["Access-Control-Allow-Origin"] == origin
    assert headers["Access-Control-Allow-Headers"] == "Authorization, Content-Type"
    assert headers["Access-Control-Allow-Private-Network"] == "true"
    assert "Access-Control-Allow-Credentials" not in headers
    assert headers["Vary"] == "Origin"
    for method, extra in [
        ("TRACE", {}),
        ("GET", {"Access-Control-Request-Headers": "X-Arbitrary"}),
    ]:
        assert exchange("OPTIONS", **{"Access-Control-Request-Method": method, **extra})[0] == 403
    assert exchange("OPTIONS", "/", **{"Access-Control-Request-Method": "GET"})[0] == 404
    status, headers, _ = exchange("GET")
    assert status == 401
    assert headers["Access-Control-Allow-Origin"] == origin
    assert exchange("GET", Authorization=f"Bearer {api.token}")[0] == 200
    status, headers, _ = exchange(
        "GET", Origin="https://evil.example", Authorization=f"Bearer {api.token}"
    )
    assert status == 403
    assert "Access-Control-Allow-Origin" not in headers
    assert exchange("GET", Host="evil.example", Authorization=f"Bearer {api.token}")[0] == 403


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


@pytest.mark.parametrize("incremental", [False, True])
def test_job_exposes_live_progress_before_completion(tmp_path, incremental):
    manager = JobManager(tmp_path)
    try:
        job = manager.submit(
            workflow(
                "def Execute() -> tuple[int]:\n    import time\n    time.sleep(0.5)\n    return (1,)\n"
            ),
            {"session_id": "progress"} if incremental else None,
        )
        deadline = time.monotonic() + 20
        saw_running = False
        while time.monotonic() < deadline:
            job = manager.get(job["id"])
            saw_running |= any(event["state"] == "running" for event in job["progress"])
            if job["state"] != "running":
                break
            time.sleep(0.01)
        assert saw_running
        assert job["state"] == "completed", job
        assert job["progress"] == job["result"]["progress"]
        assert job["progress"][0]["elapsed_seconds"] >= 0.5
    finally:
        manager.close()


@pytest.mark.parametrize("incremental", [False, True])
def test_job_result_cursor_only_returns_new_nodes(tmp_path, incremental):
    payload = workflow()
    payload["nodes"].append(
        {
            "id": "slow-failure",
            "definition_id": "user-function",
            "parameters": {
                "code": "def Execute() -> tuple[int]:\n    import time\n    time.sleep(0.5)\n"
                '    raise ValueError("failure")\n'
            },
        }
    )
    manager = JobManager(tmp_path)
    try:
        job = manager.submit(payload, {"session_id": "deltas"} if incremental else None)
        cursor = 0
        deltas = []
        saw_live_result = False
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            job = manager.get(job["id"], cursor)
            if job["state"] == "running" and job["node_results"]:
                saw_live_result = True
            deltas.extend(job["node_results"])
            cursor = job["result_cursor"]
            if job["state"] != "running":
                break
            time.sleep(0.01)
        assert saw_live_result
        assert job["state"] == "failed", job
        assert [delta["node_id"] for delta in deltas] == ["source", "output"]
        assert manager.get(job["id"], cursor)["node_results"] == []
        assert job["result"]["partial"]["outputs"]["source"] == {"value": "hello"}
        with pytest.raises(ValueError, match="cursor"):
            manager.get(job["id"], cursor + 1)
    finally:
        manager.close()


def test_http_result_cursor(api):
    status, runtime = request(api, "GET", "/api/v1/runtime")
    assert status == 200
    assert runtime["capabilities"]["liveNodeResults"] == 1
    status, job = request(api, "POST", "/api/v1/executions", {"workflow": workflow()})
    assert status == 202
    job = wait_job(api, job["id"])
    assert [delta["node_id"] for delta in job["node_results"]] == ["source", "output"]
    path = f"/api/v1/executions/{job['id']}?after={job['result_cursor']}"
    status, next_poll = request(api, "GET", path)
    assert status == 200
    assert next_poll["node_results"] == []
    assert next_poll["result_cursor"] == job["result_cursor"]
    assert request(api, "GET", path.replace("after=2", "after=-1"))[0] == 400


def test_package_api_opt_in_metadata_and_idle_session_refresh(api, monkeypatch):
    status, runtime = request(api, "GET", "/api/v1/runtime")
    assert status == 200
    assert runtime["capabilities"]["installPackages"] is False
    assert runtime["packageInstallation"]["persistent"] is True
    assert request(api, "POST", "/api/v1/packages/check", {"name": "example"})[0] == 403
    api.packages.enabled = True
    plan = {"token": "confirmed", "packages": [], "persistent": True}
    monkeypatch.setattr(api.packages, "check", lambda name: plan)
    monkeypatch.setattr(api.packages, "install", lambda token: plan)
    assert request(api, "POST", "/api/v1/packages/check", {"name": "example"}) == (200, plan)
    disposed = []
    api.jobs.sessions["idle"] = None
    monkeypatch.setattr(api.jobs, "dispose_session", lambda session: disposed.append(session))
    assert request(api, "POST", "/api/v1/packages/install", {"token": "confirmed"}) == (200, plan)
    assert disposed == ["idle"]
    api.jobs.sessions.clear()
    api.jobs.active = "running"
    try:
        assert request(api, "POST", "/api/v1/packages/install", {"token": "confirmed"})[0] == 409
    finally:
        api.jobs.active = None


def test_incremental_session_retains_objects_and_disposal_starts_cold(api):
    options = {"session_id": "test-session"}
    status, job = request(
        api,
        "POST",
        "/api/v1/executions",
        {
            "workflow": workflow(),
            "options": options,
        },
    )
    assert status == 202
    first = wait_job(api, job["id"])["result"]
    assert first["status"] == "ok"
    worker = api.jobs.sessions["test-session"][0]
    _, job = request(
        api,
        "POST",
        "/api/v1/executions",
        {
            "workflow": workflow(),
            "options": options,
        },
    )
    second = wait_job(api, job["id"])["result"]
    assert second["execution_order"] == []
    assert set(second["cache"]["reused"]) == {"source", "output"}
    assert second["outputs"] == first["outputs"]
    assert api.jobs.sessions["test-session"][0] is worker
    assert request(api, "POST", "/api/v1/execution-sessions/dispose", options)[0] == 200
    assert worker.poll() is not None
    _, job = request(
        api,
        "POST",
        "/api/v1/executions",
        {
            "workflow": workflow(),
            "options": options,
        },
    )
    third = wait_job(api, job["id"])["result"]
    assert third["execution_order"] == ["source", "output"]
    assert third["cache"]["epoch"] != second["cache"]["epoch"]


def test_incremental_cancel_loses_session_and_recovers(api):
    options = {"session_id": "cancel-test"}
    _, job = request(
        api,
        "POST",
        "/api/v1/executions",
        {
            "workflow": workflow("def Execute():\n    while True: pass\n"),
            "options": options,
        },
    )
    worker = api.jobs.sessions["cancel-test"][0]
    assert request(api, "POST", f"/api/v1/executions/{job['id']}/cancel", {})[0] == 200
    assert worker.poll() is not None
    _, job = request(
        api,
        "POST",
        "/api/v1/executions",
        {
            "workflow": workflow(),
            "options": options,
        },
    )
    assert wait_job(api, job["id"])["result"]["status"] == "ok"


def test_runtime_catalog_and_authentication(api):
    status, runtime = request(api, "GET", "/api/v1/runtime")
    assert status == 200
    assert runtime["version"] == 1
    assert runtime["kind"] == "native"
    assert runtime["workflow_format_version"] == 3
    assert runtime["capabilities"]["mountDirectory"] is False
    assert "numpy" in runtime["packages"]
    assert runtime["versions"]["Python"]
    for name in ("pyimagej", "cosapp", "pyplaid"):
        assert name in runtime["versions"]
        assert runtime["versions"][name] is None or isinstance(runtime["versions"][name], str)
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


@pytest.mark.parametrize("verbose", [False, True])
def test_server_activity_diagnostics_are_opt_in_and_redacted(api, capsys, verbose):
    api.verbose = verbose
    api.jobs.verbose = verbose
    route = "/api/v1/files/content?" + urlencode({"path": "private-name.txt", "token": api.token})
    assert request(api, "PUT", route, b"private-file-content")[0] == 200
    assert request(api, "GET", "/private-unknown-path")[0] == 404
    assert request(api, "GET", "/api/v1/runtime", headers={"Authorization": "secret"})[0] == 401
    _, job = request(api, "POST", "/api/v1/executions", {"workflow": workflow()})
    assert wait_job(api, job["id"])["state"] == "completed"
    for _ in range(2):
        request(api, "GET", f"/api/v1/executions/{job['id']}")
    output = capsys.readouterr()
    assert output.out == ""
    if not verbose:
        assert output.err == ""
        return
    assert "HTTP PUT /api/v1/files/content -> 200" in output.err
    assert "HTTP GET <unknown endpoint> -> 404" in output.err
    assert "HTTP GET /api/v1/runtime -> 401" in output.err
    assert output.err.count(f"Execution {job['id']}: running") == 1
    assert output.err.count(f"Execution {job['id']}: completed") == 1
    assert output.err.count(f"Execution {job['id']}: Node 'source' output 'value' = 'hello'") == 1
    for private in (
        api.token,
        "secret",
        "private-name",
        "private-unknown",
        "private-file",
    ):
        assert private not in output.err


@pytest.mark.parametrize("verbose", [False, True])
@pytest.mark.parametrize("incremental", [False, True])
def test_node_console_output_is_opt_in(tmp_path, capfd, verbose, incremental):
    manager = JobManager(tmp_path, verbose=verbose)
    options = {"session_id": "console"} if incremental else None
    code = (
        "def Execute() -> tuple[str]:\n"
        "    import sys\n"
        "    import logging\n"
        "    print('node-stdout-marker')\n"
        "    print('node-stderr-marker', file=sys.stderr)\n"
        "    logging.warning('node-log-marker')\n"
        "    return ('node-value-marker',)\n"
    )
    try:
        for run in range(3 if incremental else 1):
            run_options = {**options, "from_scratch": True} if run == 2 else options
            job = manager.submit(workflow(code), run_options)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                job = manager.get(job["id"])
                if job["state"] != "running":
                    break
                time.sleep(0.02)
            assert job["state"] == "completed", job
            for _ in range(2):
                manager.get(job["id"])
            output = capfd.readouterr()
            if verbose:
                # Cached results are reported again, but cached code does not print.
                executions = 0 if incremental and run == 1 else 1
                assert output.out.count("node-stdout-marker") == executions
                assert output.err.count("node-stderr-marker") == executions
                assert output.err.count("node-log-marker") == executions
                assert output.err.count("node-value-marker") == 1
                assert f"Execution {job['id']}: Node 'python' output" in output.err
            else:
                assert output.out == output.err == ""
    finally:
        manager.close()


def test_node_console_summaries_are_bounded_and_do_not_mutate_values(tmp_path, capsys):
    manager = JobManager(tmp_path, verbose=True)
    value = ["x" * 10000] * 10000
    result = {"node_id": "large", "nodes": {"outputs": {"large": {"data": value}}}}
    try:
        manager._report_node_outputs("job", result)
        output = capsys.readouterr()
        assert output.out == ""
        assert "Node 'large' output 'data'" in output.err
        assert "..." in output.err
        assert len(output.err) < 2000
        assert result["nodes"]["outputs"]["large"]["data"] is value
        assert len(value) == 10000
        assert len(value[0]) == 10000
    finally:
        manager.close()


def test_verbose_job_failure_cancellation_and_timeout(api, capsys):
    api.jobs.verbose = True
    _, failed = request(api, "POST", "/api/v1/executions", {"workflow": {}})
    assert wait_job(api, failed["id"])["state"] == "failed"
    _, cancelled = request(api, "POST", "/api/v1/executions", {"workflow": workflow()})
    assert request(api, "POST", f"/api/v1/executions/{cancelled['id']}/cancel", {})[0] == 200
    api.jobs.timeout = 0.001
    _, expired = request(api, "POST", "/api/v1/executions", {"workflow": workflow()})
    completed = wait_job(api, expired["id"])
    assert completed["state"] == "completed"
    assert completed["timed_out"] is True
    output = capsys.readouterr().err
    assert f"Execution {failed['id']}: failed" in output
    assert output.count(f"Execution {cancelled['id']}: cancelled") == 1
    assert f"Execution {cancelled['id']}: failed" not in output
    assert f"Execution {expired['id']}: running (timeout reached; worker retained)" in output


@pytest.mark.parametrize("option", ["--verbose", "-v"])
def test_cli_verbose_lifecycle(tmp_path, monkeypatch, capsys, option):
    from http.server import ThreadingHTTPServer

    def interrupt(self, poll_interval):
        raise KeyboardInterrupt

    monkeypatch.setattr(ThreadingHTTPServer, "serve_forever", interrupt)
    assert main(["serve", "--workspace", str(tmp_path), "--port", "0", option]) == 0
    output = capsys.readouterr()
    assert "Bearer token:" in output.out
    assert "Bearer token:" not in output.err
    states = ["starting", "ready/listening", "shutting down", "stopped"]
    positions = [output.err.index(f"Server state: {state}") for state in states]
    assert positions == sorted(positions)
    assert f"Workspace: {str(tmp_path.resolve())!r}" in output.err
    assert "Allowed editor origins: ['https://flowgraph-web.fbw-es.com']" in output.err
    assert "Limits: execution=120s, request=16777216 bytes" in output.err


def test_execution_state_recovery_is_authenticated_and_read_only(api):
    assert request(api, "GET", "/api/v1/runtime")[1]["capabilities"]["executionRecovery"] == 1
    assert request(api, "GET", "/api/v1/execution-state")[0] == 404
    assert (
        request(api, "GET", "/api/v1/execution-state", headers={"Authorization": "Bearer wrong"})[0]
        == 401
    )
    submitted = workflow()
    options = {"session_id": "recover-me"}
    status, job = request(
        api, "POST", "/api/v1/executions", {"workflow": submitted, "options": options}
    )
    assert status == 202
    status, snapshot = request(api, "GET", "/api/v1/execution-state")
    assert status == 200
    assert snapshot["workflow"] == submitted
    assert snapshot["options"] == options
    assert snapshot["job"]["id"] == job["id"]
    finished = wait_job(api, job["id"])
    assert request(api, "GET", "/api/v1/execution-state")[1]["job"] == finished
    status, selected = request(
        api,
        "POST",
        "/api/v1/executions",
        {"workflow": submitted, "options": {**options, "targets": ["source"]}},
    )
    assert status == 202
    snapshot = request(api, "GET", "/api/v1/execution-state")[1]
    assert snapshot["job"]["id"] == selected["id"]
    assert snapshot["previous_result"] == finished["result"]
    wait_job(api, selected["id"])
    assert len(api.jobs.jobs) == 2  # Recovery must never submit another execution.


def test_execution_state_can_reconnect_and_cancel_running_job(api):
    submitted = workflow(
        "def Execute() -> tuple[int]:\n    import time\n    time.sleep(30)\n    return (1,)\n"
    )
    status, job = request(api, "POST", "/api/v1/executions", {"workflow": submitted})
    assert status == 202
    snapshot = request(api, "GET", "/api/v1/execution-state")[1]
    assert snapshot["job"]["state"] == "running"
    assert api.jobs.process.poll() is None
    request(api, "POST", f"/api/v1/executions/{job['id']}/cancel", b"")
    assert request(api, "GET", "/api/v1/execution-state")[1]["job"]["state"] == "cancelled"


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


def test_directory_download_and_delete_over_http(api):
    api.workspace.write("folder/nested/input.txt", b"contents")
    (api.workspace.root / "folder/empty").mkdir()
    route = "/api/v1/files/content?" + urlencode({"path": "folder"})
    status, data = request(api, "GET", route)
    assert status == 200
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.read("folder/nested/input.txt") == b"contents"
        assert "folder/empty/" in archive.namelist()
    status, listing = request(api, "DELETE", route)
    assert status == 200
    assert listing["files"] == []
    assert listing["directories"] == []
    assert not (api.workspace.root / "folder").exists()


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


def test_create_empty_workspace_directory_then_upload_into_it(api):
    route = "/api/v1/files/directories"
    assert request(api, "GET", "/api/v1/runtime")[1]["capabilities"]["createDirectory"] is True
    assert request(api, "POST", route, {"path": "data"}, {"Authorization": ""})[0] == 401
    assert request(api, "POST", route, {"path": "data"}) == (201, {"status": "ok"})
    assert request(api, "POST", route, {"path": "data/empty dir"})[0] == 201
    assert request(api, "POST", route, {"path": "data/empty dir"})[0] == 409
    assert request(api, "POST", route, {"path": "missing/child"})[0] == 404
    assert request(api, "POST", route, {})[0] == 400
    _, listing = request(api, "GET", "/api/v1/files")
    assert listing["directories"] == ["data", "data/empty dir"]
    assert listing["files"] == []
    upload = "/api/v1/files/content?" + urlencode({"path": "data/empty dir/input.bin"})
    assert (
        request(api, "PUT", upload, b"\x00\xff", {"Content-Type": "application/octet-stream"})[0]
        == 200
    )
    assert request(api, "GET", upload) == (200, b"\x00\xff")


@pytest.mark.parametrize(
    "name", ["../escape", "/etc/passwd", "a/../../escape", "a\\escape", "a//b", "a/./b"]
)
def test_file_paths_cannot_escape_workspace(api, name):
    route = "/api/v1/files/content?" + urlencode({"path": name})
    assert request(api, "PUT", route, b"bad")[0] == 400
    assert request(api, "POST", "/api/v1/files/directories", {"path": name})[0] == 400


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
    assert request(api, "POST", "/api/v1/files/directories", {"path": "link/child"})[0] == 400
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
    assert manager.get(job["id"])["state"] == "completed"
    assert manager.get(job["id"])["timed_out"] is True
    manager.timeout = 30
    job = manager.submit(workflow())
    process = manager.process
    manager.close()
    assert process.poll() is not None
    assert manager.get(job["id"])["state"] == "cancelled"
    assert all(not thread.is_alive() for thread in manager.threads)
    with pytest.raises(RuntimeError, match="closed"):
        manager.submit(workflow())


@pytest.mark.parametrize("session", [False, True])
def test_advisory_timeout_keeps_worker_alive_until_explicit_kill(api, session):
    assert (
        request(api, "GET", "/api/v1/runtime")[1]["capabilities"]["advisoryExecutionTimeout"] == 1
    )
    code = "def Execute() -> tuple[int]:\n    import time\n    time.sleep(60)\n    return (1,)\n"
    body = {"workflow": workflow(code), "timeout_seconds": 0.01}
    if session:
        body["options"] = {"session_id": "timeout-session"}
    status, job = request(api, "POST", "/api/v1/executions", body)
    assert status == 202
    process = api.jobs.process
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status, running = request(api, "GET", f"/api/v1/executions/{job['id']}")
        if running["timed_out"]:
            break
        time.sleep(0.01)
    assert running["timed_out"] is True
    assert running["state"] == "running"
    assert running["timeout_seconds"] == 0.01
    assert process.poll() is None
    assert request(api, "POST", "/api/v1/executions", {"workflow": workflow()})[0] == 409
    assert (
        request(api, "POST", f"/api/v1/executions/{job['id']}/cancel", {})[1]["state"]
        == "cancelled"
    )
    assert process.poll() is not None
    assert request(api, "GET", "/api/v1/runtime")[0] == 200
    _, retry = request(api, "POST", "/api/v1/executions", {"workflow": workflow()})
    assert wait_job(api, retry["id"])["state"] == "completed"


def test_incremental_execution_can_complete_after_timeout(api):
    status, job = request(
        api,
        "POST",
        "/api/v1/executions",
        {
            "workflow": workflow(),
            "options": {"session_id": "late-result"},
            "timeout_seconds": 0.001,
        },
    )
    assert status == 202
    completed = wait_job(api, job["id"])
    assert completed["state"] == "completed"
    assert completed["timed_out"] is True
    assert api.jobs.sessions["late-result"][0].poll() is None


@pytest.mark.parametrize("timeout", [True, "120", 0, -1, 86401, float("inf"), float("nan")])
def test_execution_timeout_validation(api, timeout):
    assert (
        request(
            api, "POST", "/api/v1/executions", {"workflow": workflow(), "timeout_seconds": timeout}
        )[0]
        == 400
    )
    assert api.jobs.active is None


@pytest.mark.parametrize("session", [False, True])
def test_worker_crash_and_result_limit_are_reported(api, session):
    options = {"options": {"session_id": "failed-worker"}} if session else {}
    crash = "def Execute() -> tuple[int]:\n    import os\n    os._exit(7)\n    return (1,)\n"
    status, job = request(
        api, "POST", "/api/v1/executions", {"workflow": workflow(crash), **options}
    )
    assert status == 202
    failed = wait_job(api, job["id"])
    assert failed["state"] == "failed"
    assert "without a result (7)" in failed["error"]
    api.jobs.max_result = 1
    status, job = request(api, "POST", "/api/v1/executions", {"workflow": workflow(), **options})
    assert status == 202
    failed = wait_job(api, job["id"])
    assert failed["state"] == "failed"
    assert "size limit" in failed["error"]
    assert api.jobs.active is None
    assert "failed-worker" not in api.jobs.sessions
    api.jobs.max_result = 64 << 20
    status, retry = request(api, "POST", "/api/v1/executions", {"workflow": workflow(), **options})
    assert status == 202
    assert wait_job(api, retry["id"])["state"] == "completed"


@pytest.mark.parametrize("oversized", [False, True])
def test_job_cleanup_failure_does_not_prevent_final_state(tmp_path, monkeypatch, caplog, oversized):
    import tempfile
    from pathlib import Path
    from unittest.mock import Mock

    temporary = tempfile.TemporaryDirectory(prefix="flowgraph-job-test-")
    root = Path(temporary.name)
    cleanup = temporary.cleanup

    def locked_cleanup():
        cleanup()
        raise PermissionError("file is being used by another process")

    monkeypatch.setattr(temporary, "cleanup", locked_cleanup)
    manager = JobManager(tmp_path, max_result=1 if oversized else 1024)
    manager.jobs["test"] = {"state": "running", "node_results": []}
    manager.active = "test"
    process = Mock()
    process.poll.return_value = None if oversized else 0
    process.returncode = 0
    manager.process = process
    (root / "response.json").write_text('{"status": "ok"}', encoding="utf-8")
    (root / "progress.jsonl").write_text('{"node_result": {}}\n', encoding="utf-8")

    manager._watch("test", process, temporary)

    job = manager.get("test")
    assert job["state"] == ("failed" if oversized else "completed")
    if oversized:
        assert "size limit" in job["error"]
        process.terminate.assert_called_once()
        process.wait.assert_called_once()
    else:
        process.terminate.assert_not_called()
    assert manager.active is None
    assert manager.process is None
    assert "Could not remove execution temporary directory" in caplog.text


@pytest.mark.parametrize(
    ("options", "expected_port", "expected_origins"),
    [
        ([], 8765, ("https://flowgraph-web.fbw-es.com",)),
        (["--port", "0"], 0, ("https://flowgraph-web.fbw-es.com",)),
        (
            ["--allow-origin", "http://127.0.0.1:8082"],
            8765,
            ("http://127.0.0.1:8082",),
        ),
        (
            [
                "--port",
                "9000",
                "--allow-origin",
                "https://editor.example",
                "--allow-origin",
                "http://localhost:8080",
            ],
            9000,
            ("https://editor.example", "http://localhost:8080"),
        ),
    ],
)
def test_cli_server_defaults_and_overrides(
    tmp_path, monkeypatch, capsys, options, expected_port, expected_origins
):
    from flowgraph.server import http

    configuration = {}

    class StubServer:
        origin = "http://127.0.0.1:8765"
        token = "test-token"

        def __init__(self, workspace, **kwargs):
            configuration.update(workspace=workspace, **kwargs)
            self.origin = f"http://127.0.0.1:{kwargs['port'] or 45678}"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def serve_forever(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(http, "LocalServer", StubServer)
    assert main(["serve", "--workspace", str(tmp_path), *options]) == 0
    assert configuration["workspace"] == tmp_path
    assert configuration["port"] == expected_port
    assert configuration["allowed_origins"] == expected_origins
    assert configuration["verbose"] is False
    captured = capsys.readouterr()
    assert captured.err == ""
    output = captured.out
    assert "Experimental FlowGraph API" in output
    assert (
        f"Open editor: {expected_origins[0]}/#token=test-token&port={expected_port or 45678}\n"
        in output
    )
    assert "Bearer token: test-token" in output

    assert "editor_dir" not in configuration
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args(
            ["serve", "--workspace", str(tmp_path), "--editor-dir", str(tmp_path)]
        )
    assert error.value.code == 2


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


@pytest.mark.parametrize(
    "public_url",
    [
        "http://python.example",
        "https://user:pass@python.example",
        "https://python.example/api",
        "https://python.example?token=x",
        "https://python.example#x",
        "https://python.example:bad",
        "https://python.example\r\nInjected: yes",
    ],
)
def test_remote_configuration_rejects_unsafe_public_urls(tmp_path, public_url):
    with pytest.raises(ValueError):
        LocalServer(tmp_path, port=0, public_url=public_url)


def test_non_loopback_binding_requires_https_proxy_configuration(tmp_path):
    with pytest.raises(ValueError, match="HTTPS reverse proxy"):
        LocalServer(tmp_path, port=0, host="0.0.0.0")


@pytest.mark.parametrize("public_url", ["https://192.168.1.20:9443", "https://python.example"])
def test_https_proxy_preserves_host_origin_cors_and_auth(tmp_path, public_url):
    editor = "https://editor.example"
    with LocalServer(
        tmp_path, port=0, host="0.0.0.0", public_url=public_url, allowed_origins=(editor,)
    ) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            headers = {"Host": server.authority, "Origin": editor, "Sec-Fetch-Site": "cross-site"}
            assert server.origin == public_url
            assert request(server, "GET", "/api/v1/runtime", headers=headers)[0] == 200
            assert (
                request(server, "GET", "/api/v1/runtime", headers={**headers, "Authorization": ""})[
                    0
                ]
                == 401
            )
            assert (
                request(
                    server, "GET", "/api/v1/runtime", headers={**headers, "Host": "evil.example"}
                )[0]
                == 403
            )
            assert (
                request(
                    server,
                    "GET",
                    "/api/v1/runtime",
                    headers={**headers, "Origin": "https://evil.example"},
                )[0]
                == 403
            )
            assert (
                request(
                    server,
                    "OPTIONS",
                    "/api/v1/runtime",
                    headers={
                        **headers,
                        "Access-Control-Request-Method": "GET",
                        "Access-Control-Request-Headers": "authorization",
                    },
                )[0]
                == 200
            )
        finally:
            server.shutdown()
            thread.join(timeout=5)


def test_cli_remote_launch_link(tmp_path, monkeypatch, capsys):
    from urllib.parse import parse_qs, urlsplit

    def interrupt(self):
        raise KeyboardInterrupt

    monkeypatch.setattr(LocalServer, "serve_forever", interrupt)
    assert (
        main(
            [
                "serve",
                "--workspace",
                str(tmp_path),
                "--port",
                "0",
                "--public-url",
                "https://python.example",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    launch = next(
        line.removeprefix("Open editor: ")
        for line in output.splitlines()
        if line.startswith("Open editor: ")
    )
    fragment = parse_qs(urlsplit(launch).fragment)
    assert fragment["backend"] == ["https://python.example"]
    assert len(fragment["token"][0]) >= 32
    assert "HTTPS proxy required" in output


def test_server_never_hosts_editor_or_workspace_assets(tmp_path):
    (tmp_path / "index.html").write_text("private workspace content")
    (tmp_path / "native-bootstrap.js").write_text("private script")
    with LocalServer(tmp_path, port=0) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            assert (
                request(server, "GET", "/api/v1/runtime", headers={"Authorization": ""})[0] == 401
            )
            for path in (
                "/",
                "/index.html",
                "/native-bootstrap.js",
                "/flowgraph-editor.json",
                "/../secret.py",
                "/%2e%2e/secret.py",
                "/secret.py",
                "/private/secret.json",
                "/vendor/",
                "/.git/config",
            ):
                assert request(server, "GET", path)[0] in {403, 404}
            assert request(server, "GET", "/", headers={"Host": "evil.example"})[0] == 403
            assert not hasattr(server, "editor_dir")
            assert not hasattr(server, "launch_url")
        finally:
            server.shutdown()
            thread.join(timeout=5)
