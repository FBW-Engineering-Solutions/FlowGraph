"""Workspace references remain portable without rewriting saved graphs."""

import json
from pathlib import Path

import pytest

from flowgraph.adapters.data_types import DIRECTORY
from flowgraph.adapters.files import READ_DIRECTORY_FILES, SELECT_SERVER_FILE, WORKSPACE
from flowgraph.adapters.simple_sources import SET_STRING
from flowgraph.adapters.workflow import RUN_WORKFLOW
from flowgraph.adapters.workflow_interfaces import WORKFLOW_OUTPUT
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_cli import execute_cli_workflow
from flowgraph.application.workflow_core import (
    ExecContext,
    WorkflowEdge,
    WorkflowExecutor,
    WorkflowGraph,
)
from flowgraph.application.workflow_execution import execute_workflow_json
from flowgraph.application.workflow_io import save_workflow, workflow_to_dict
from flowgraph.application.workflow_session import WorkflowSession
from flowgraph.core_cli import main
from flowgraph.server.jobs import JobManager


def workflow_to_json(graph):
    return json.dumps(workflow_to_dict(graph))


def file_graph():
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            SELECT_SERVER_FILE.create_instance(
                "file", parameters={"file name": "my/files/mesh.stl"}
            ),
            WORKFLOW_OUTPUT.create_instance("output", parameters={"name": "path"}),
        ]
    )
    graph.add_edge(WorkflowEdge("file", "path", "output", "value"), registry)
    graph.sync_boundary_nodes(registry)
    return registry, graph


def workspace_at(root):
    source = root / "my/files/mesh.stl"
    source.parent.mkdir(parents=True)
    source.write_text("mesh placeholder", encoding="utf-8")
    return root


def test_workspace_node_contract_and_missing_context(tmp_path):
    registry = create_node_registry()
    assert SELECT_SERVER_FILE.id == "workspace-file"
    assert registry.require("workspace-file") is SELECT_SERVER_FILE
    assert registry.get("select-server-file") is None
    assert WORKSPACE.id == "workspace-folder"
    assert registry.require("workspace-folder") is WORKSPACE
    assert registry.get("workspace") is None
    assert WORKSPACE.label == "Workspace Folder"
    assert WORKSPACE.parameters[0].name == "folder"
    assert WORKSPACE.parameters[0].default == "."
    assert WORKSPACE.parameters[0].kind.id == "string"
    assert WORKSPACE.cache_policy == "pure"
    assert WORKSPACE.outputs[0].data_type is DIRECTORY
    result = WORKSPACE.executor({}, {}, ExecContext(workspace=tmp_path))
    assert result == {"path": tmp_path}
    assert isinstance(result["path"], Path)
    with pytest.raises(ValueError, match="configured workspace"):
        WORKSPACE.executor({}, {})


def test_workspace_directory_relocation_and_listing(tmp_path):
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            WORKSPACE.create_instance("workspace", parameters={"folder": "nested/empty"}),
            READ_DIRECTORY_FILES.create_instance("listing"),
        ]
    )
    graph.add_edge(WorkflowEdge("workspace", "path", "listing", "path"), registry)
    assert graph.edge_conversion(graph.edges[0], registry) is None
    saved = workflow_to_json(graph)
    session = WorkflowSession(registry)
    for name in ("first", "moved"):
        root = tmp_path / name
        root.mkdir()
        folder = root / "nested/empty"
        folder.mkdir(parents=True)
        (folder / "mesh.stl").write_text("mesh", encoding="utf-8")
        result = session.run(graph, workspace=root)
        assert result.node_outputs["workspace"] == {"path": folder}
        assert isinstance(result.node_outputs["workspace"]["path"], Path)
        assert isinstance(result.node_inputs["listing"]["path"], Path)
        assert result.node_outputs["listing"]["files_full_paths"] == [str(folder / "mesh.stl")]
        assert "workspace" in session.metadata["executed"]
        session.run(graph, workspace=root)
        assert "workspace" in session.metadata["reused"]
        assert workflow_to_json(graph) == saved


@pytest.mark.parametrize(
    "selected, message",
    [
        ("missing", "does not exist"),
        ("file.txt", "not a directory"),
        ("../outside", "escapes"),
        ("/outside", "workspace-relative"),
        ("\\outside", "workspace-relative"),
        ("C:\\outside", "workspace-relative"),
        ("C:outside", "workspace-relative"),
        ("\\\\server\\share\\outside", "workspace-relative"),
        (None, "must be text"),
    ],
)
def test_workspace_folder_invalid_selection(tmp_path, selected, message):
    (tmp_path / "file.txt").write_text("file", encoding="utf-8")
    with pytest.raises((ValueError, TypeError), match=message):
        WORKSPACE.executor({}, {"folder": selected}, ExecContext(workspace=tmp_path))


def test_workspace_folder_rejects_symlink_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "outside").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes"):
        WORKSPACE.executor({}, {"folder": "outside"}, ExecContext(workspace=root))


@pytest.mark.parametrize("as_path", [False, True])
@pytest.mark.parametrize("selected", ["new/output", "../outside", "existing.txt"])
def test_workspace_folder_connected_override(tmp_path, selected, as_path):
    (tmp_path / "existing.txt").write_text("file", encoding="utf-8")
    value = Path(selected) if as_path else selected
    assert WORKSPACE.executor(
        {"folder": value}, {"folder": "saved"}, ExecContext(workspace=tmp_path)
    ) == {"path": (tmp_path / selected).resolve()}
    assert not (tmp_path / "new").exists()


@pytest.mark.parametrize("as_path", [False, True])
def test_workspace_folder_absolute_override_without_context(tmp_path, as_path):
    folder = tmp_path / "new/output"
    assert WORKSPACE.executor({"folder": folder if as_path else str(folder)}, {}) == {
        "path": folder
    }
    assert not folder.exists()


@pytest.mark.parametrize("value", ["", None, 42])
def test_workspace_folder_invalid_connected_value(value):
    with pytest.raises((ValueError, TypeError)):
        WORKSPACE.executor({"folder": value}, {})


def test_workspace_folder_relative_override_requires_context():
    with pytest.raises(ValueError, match="configured workspace"):
        WORKSPACE.executor({"folder": "new/output"}, {})


@pytest.mark.parametrize("path_source", [False, True])
def test_workspace_folder_override_is_branch_local_and_preserves_fallback(tmp_path, path_source):
    registry = create_node_registry()
    saved = tmp_path / "saved"
    saved.mkdir()
    source = (
        WORKSPACE.create_instance("source")
        if path_source
        else SET_STRING.create_instance("source", parameters={"value": "new/output"})
    )
    branch = WORKSPACE.create_instance("branch", parameters={"folder": "saved"})
    graph = WorkflowGraph([source, branch, WORKSPACE.create_instance("other")])
    edge = WorkflowEdge("source", "path" if path_source else "value", "branch", "folder")
    graph.add_edge(edge, registry)
    original = workflow_to_json(graph)
    session = WorkflowSession(registry)
    result = session.run(graph, workspace=tmp_path)
    assert result.node_outputs["branch"]["path"] == (
        tmp_path if path_source else tmp_path / "new/output"
    )
    assert result.node_outputs["other"]["path"] == tmp_path
    assert workflow_to_json(graph) == original
    session.run(graph, workspace=tmp_path)
    assert "branch" in session.metadata["reused"]
    if not path_source:
        source.parameters["value"] = "different/output"
        result = session.run(graph, workspace=tmp_path)
        assert result.node_outputs["branch"]["path"] == tmp_path / "different/output"
        assert result.node_outputs["other"]["path"] == tmp_path
        assert "branch" in session.metadata["executed"]
    graph.remove_edge(edge, registry)
    result = session.run(graph, workspace=tmp_path)
    assert result.node_outputs["branch"]["path"] == saved
    assert branch.parameters["folder"] == "saved"


@pytest.mark.parametrize("incremental", [False, True])
def test_workspace_folder_connected_json_execution(tmp_path, incremental):
    registry = create_node_registry()
    destination = tmp_path / "new/output"
    graph = WorkflowGraph(
        [
            SET_STRING.create_instance("source", parameters={"value": str(destination)}),
            WORKSPACE.create_instance("folder"),
        ]
    )
    graph.add_edge(WorkflowEdge("source", "value", "folder", "folder"), registry)
    response = json.loads(
        execute_workflow_json(
            workflow_to_json(graph),
            {"session_id": "folder-override"} if incremental else None,
        )
    )
    assert response["status"] == "ok"
    assert response["nodes"]["outputs"]["folder"]["path"] == str(destination)
    assert not destination.exists()


@pytest.mark.parametrize("incremental", [False, True])
def test_workspace_directory_nested_and_json_execution(tmp_path, incremental):
    registry = create_node_registry()
    child = WorkflowGraph(
        [
            WORKSPACE.create_instance("workspace"),
            WORKFLOW_OUTPUT.create_instance("output", parameters={"name": "path"}),
        ]
    )
    child.add_edge(WorkflowEdge("workspace", "path", "output", "value"), registry)
    child.sync_boundary_nodes(registry)
    wrapper = RUN_WORKFLOW.create_instance("nested")
    wrapper.subworkflows = {"default": child}
    graph = WorkflowGraph([wrapper])
    response = json.loads(
        execute_workflow_json(
            workflow_to_json(graph),
            {"session_id": "workspace-directory"} if incremental else None,
            workspace=tmp_path,
        )
    )
    assert response["status"] == "ok"
    assert response["nodes"]["outputs"]["nested"]["path"] == str(tmp_path)


def test_relocation_and_cache_invalidation(tmp_path):
    registry, graph = file_graph()
    saved = workflow_to_json(graph)
    session = WorkflowSession(registry)
    for name in ("first", "relocated"):
        root = workspace_at(tmp_path / name)
        result = session.run(graph, workspace=root)
        assert result.node_outputs["file"]["path"] == str(root / "my/files/mesh.stl")
        assert "file" in session.metadata["executed"]
        assert workflow_to_json(graph) == saved
        session.run(graph, workspace=root)
        assert "file" in session.metadata["reused"]


@pytest.mark.parametrize(
    "path, message",
    [
        ("missing.stl", "does not exist"),
        ("my/files", "not a file"),
        ("../outside.stl", "escapes"),
    ],
)
def test_invalid_workspace_files(tmp_path, path, message):
    root = workspace_at(tmp_path / "project")
    with pytest.raises(ValueError, match=message):
        SELECT_SERVER_FILE.executor({}, {"file name": path}, ExecContext(workspace=root))


def test_symlink_escape(tmp_path):
    root = workspace_at(tmp_path / "project")
    external = tmp_path / "outside.stl"
    external.write_text("external", encoding="utf-8")
    (root / "link.stl").symlink_to(external)
    with pytest.raises(ValueError, match="escapes"):
        SELECT_SERVER_FILE.executor({}, {"file name": "link.stl"}, ExecContext(workspace=root))


def test_missing_workspace_and_legacy_absolute_path(tmp_path):
    with pytest.raises(ValueError, match="configured workspace"):
        SELECT_SERVER_FILE.executor({}, {"file name": "mesh.stl"})
    absolute = str(tmp_path / "legacy.stl")
    assert SELECT_SERVER_FILE.executor({}, {"file name": absolute}) == {"path": absolute}
    with pytest.raises(ValueError, match="Workspace directory does not exist"):
        ExecContext(workspace=tmp_path / "missing")


@pytest.mark.parametrize("override_workspace", [False, True])
@pytest.mark.parametrize("override_file", [False, True])
def test_workspace_file_optional_overrides(tmp_path, override_workspace, override_file):
    root = workspace_at(tmp_path / "host")
    alternate = workspace_at(tmp_path / "alternate")
    for directory in (root, alternate):
        (directory / "other.stl").write_text("other", encoding="utf-8")
    inputs = {}
    if override_workspace:
        inputs["workspace"] = str(alternate)
    if override_file:
        inputs["file name"] = "other.stl"
    parameters = {"file name": "my/files/mesh.stl"}
    expected_root = alternate if override_workspace else root
    expected_file = "other.stl" if override_file else "my/files/mesh.stl"
    assert SELECT_SERVER_FILE.executor(inputs, parameters, ExecContext(workspace=root)) == {
        "path": str(expected_root / expected_file)
    }
    assert parameters == {"file name": "my/files/mesh.stl"}


@pytest.mark.parametrize("as_text", [False, True])
def test_workspace_file_override_without_host_workspace(tmp_path, as_text):
    root = workspace_at(tmp_path / "project")
    workspace = str(root) if as_text else root
    assert SELECT_SERVER_FILE.executor(
        {"workspace": workspace, "file name": "my/files/mesh.stl"}, {}
    ) == {"path": str(root / "my/files/mesh.stl")}


@pytest.mark.parametrize("incremental", [False, True])
def test_workspace_file_connected_overrides_json_execution(tmp_path, incremental):
    root = tmp_path / "new-project"
    registry, graph = file_graph()
    graph.add_node(SET_STRING.create_instance("root", parameters={"value": str(root)}))
    graph.add_node(SET_STRING.create_instance("name", parameters={"value": "my/files/mesh.stl"}))
    graph.add_edge(WorkflowEdge("root", "value", "file", "workspace"), registry)
    graph.add_edge(WorkflowEdge("name", "value", "file", "file name"), registry)
    response = json.loads(
        execute_workflow_json(
            workflow_to_json(graph),
            {"session_id": "workspace-overrides"} if incremental else None,
        )
    )
    assert response["status"] == "ok"
    assert response["nodes"]["outputs"]["file"]["path"] == str(root / "my/files/mesh.stl")
    assert not root.exists()


@pytest.mark.parametrize("workspace", ["", 42, None])
def test_workspace_file_invalid_workspace_override(tmp_path, workspace):
    with pytest.raises((ValueError, TypeError), match="workspace"):
        SELECT_SERVER_FILE.executor(
            {"workspace": workspace, "file name": "mesh.stl"}, {}, ExecContext(workspace=tmp_path)
        )


@pytest.mark.parametrize("selected", ["", None])
def test_workspace_file_override_requires_nonempty_text(tmp_path, selected):
    with pytest.raises((ValueError, TypeError)):
        SELECT_SERVER_FILE.executor({"workspace": tmp_path, "file name": selected}, {})


@pytest.mark.parametrize("connected", ["workspace", "file name", "both"])
@pytest.mark.parametrize("selected", ["../outside.stl", "link.stl", "new/output.stl", "."])
def test_workspace_file_connected_paths_skip_filesystem_validation(tmp_path, connected, selected):
    root = workspace_at(tmp_path / "project")
    outside = tmp_path / "outside.stl"
    outside.write_text("outside", encoding="utf-8")
    (root / "link.stl").symlink_to(outside)
    inputs = {}
    if connected in {"workspace", "both"}:
        inputs["workspace"] = root
    if connected in {"file name", "both"}:
        inputs["file name"] = selected
    assert SELECT_SERVER_FILE.executor(
        inputs, {"file name": selected}, ExecContext(workspace=root)
    ) == {"path": str((root / selected).resolve())}


def test_workspace_file_connected_workspace_can_be_missing(tmp_path):
    root = tmp_path / "new-workspace"
    assert SELECT_SERVER_FILE.executor({"workspace": root}, {"file name": "new/output.stl"}) == {
        "path": str(root / "new/output.stl")
    }
    assert not root.exists()


@pytest.mark.parametrize("text_workspace", [False, True])
def test_connected_workspace_file_overrides_and_cache(tmp_path, text_workspace):
    registry, graph = file_graph()
    workspace_source = (
        SET_STRING.create_instance("root") if text_workspace else WORKSPACE.create_instance("root")
    )
    graph.add_node(workspace_source)
    filename = SET_STRING.create_instance("name", parameters={"value": "other.stl"})
    graph.add_node(filename)
    graph.add_edge(
        WorkflowEdge("root", "value" if text_workspace else "path", "file", "workspace"), registry
    )
    graph.add_edge(WorkflowEdge("name", "value", "file", "file name"), registry)
    assert graph.edge_conversion(graph.edges[-2], registry) is None
    session = WorkflowSession(registry)
    for name in ("first", "moved"):
        root = workspace_at(tmp_path / name)
        (root / "other.stl").write_text("other", encoding="utf-8")
        if text_workspace:
            workspace_source.parameters["value"] = str(root)
        saved = workflow_to_json(graph)
        result = session.run(graph, workspace=root)
        assert result.node_outputs["file"]["path"] == str(root / "other.stl")
        assert "file" in session.metadata["executed"]
        session.run(graph, workspace=root)
        assert "file" in session.metadata["reused"]
        assert workflow_to_json(graph) == saved
        filename.parameters["value"] = "my/files/mesh.stl"
        result = session.run(graph, workspace=root)
        assert result.node_outputs["file"]["path"] == str(root / "my/files/mesh.stl")
        assert "file" in session.metadata["executed"]
        filename.parameters["value"] = "other.stl"
    graph.remove_edge(graph.edges[-1], registry)
    result = session.run(graph, workspace=root)
    assert result.node_outputs["file"]["path"] == str(root / "my/files/mesh.stl")
    assert (
        next(node for node in graph.nodes if node.id == "file").parameters["file name"]
        == "my/files/mesh.stl"
    )


def test_cli_and_json_execution(tmp_path, capsys):
    _registry, graph = file_graph()
    root = workspace_at(tmp_path / "project")
    workflow = tmp_path / "workflow.json"
    save_workflow(graph, workflow)
    original = workflow.read_bytes()
    _, result = execute_cli_workflow(workflow, workspace=root)
    expected = str(root / "my/files/mesh.stl")
    assert result.node_outputs["file"]["path"] == expected
    assert main(["run", str(workflow), "--workspace", str(root)]) == 0
    assert repr(expected) in capsys.readouterr().out
    for options in (None, {"session_id": "workspace-portability"}):
        response = json.loads(
            execute_workflow_json(workflow_to_json(graph), options, workspace=root)
        )
        assert response["status"] == "ok"
        assert response["nodes"]["outputs"]["file"]["path"] == expected
    assert workflow.read_bytes() == original


@pytest.mark.parametrize("incremental", [False, True])
def test_nested_workflow_inherits_workspace(tmp_path, incremental):
    registry, child = file_graph()
    wrapper = RUN_WORKFLOW.create_instance("nested")
    wrapper.subworkflows = {"default": child}
    graph = WorkflowGraph([wrapper])
    root = workspace_at(tmp_path / "project")
    runner = (
        WorkflowSession(registry) if incremental else WorkflowExecutor(registry, workspace=root)
    )
    result = runner.run(graph, **({"workspace": root} if incremental else {}))
    assert result.node_outputs["nested"]["path"] == str(root / "my/files/mesh.stl")


@pytest.mark.parametrize("incremental", [False, True])
def test_server_worker_uses_host_workspace(tmp_path, incremental):
    import time

    _registry, graph = file_graph()
    root = workspace_at(tmp_path / "project")
    manager = JobManager(root, timeout=15)
    try:
        job = manager.submit(
            workflow_to_dict(graph), {"session_id": "workspace-file"} if incremental else None
        )
        deadline = time.monotonic() + 20
        while job["state"] == "running" and time.monotonic() < deadline:
            time.sleep(0.02)
            job = manager.get(job["id"])
        assert job["state"] == "completed", job
        assert job["result"]["nodes"]["outputs"]["file"]["path"] == str(root / "my/files/mesh.stl")
    finally:
        manager.close()
