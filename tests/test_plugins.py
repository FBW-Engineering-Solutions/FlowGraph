"""Trusted file plugins across CLI, catalogs and real native worker processes."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from test_local_server import request, wait_job

from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.plugins import PluginError, load_plugin_groups, resolve_plugin_paths
from flowgraph.application.workflow_cli import (
    execute_cli_workflow,
    inspect_workflow,
    workflow_outputs,
)
from flowgraph.application.workflow_core import WorkflowEdge, WorkflowGraph
from flowgraph.application.workflow_execution import execute_workflow_json
from flowgraph.application.workflow_io import save_workflow, workflow_to_dict
from flowgraph.core_cli import main
from flowgraph.server.http import LocalServer

PLUGIN_SOURCE = """\
from dataclasses import dataclass
from flowgraph.adapters.data_types import INTEGER, ParameterKind
from flowgraph.application.workflow_core import (
    NodeDefinition, ParameterDefinition, PortDefinition, PortDirection,
)

# Dataclasses inspect sys.modules during import; plugins must be real modules.
@dataclass
class Settings:
    factor: int = 2

def scale(inputs, parameters, context):
    return {"result": inputs["value"] * parameters["factor"]}

AVAILABLE_NODES = (
    NodeDefinition(
        id="plugin-scale", icon="", label="Plugin Scale",
        ports=(
            PortDefinition("value", PortDirection.INPUT, INTEGER),
            PortDefinition("result", PortDirection.OUTPUT, INTEGER),
        ),
        parameters=(ParameterDefinition("factor", ParameterKind.INTEGER, "Factor", 2),),
        executor=scale,
    ),
)
"""


@pytest.fixture
def plugin(tmp_path):
    path = tmp_path / "custom nodes.py"
    path.write_text(PLUGIN_SOURCE, encoding="utf-8")
    return path


def plugin_workflow(registry, *, published_input=False):
    graph = WorkflowGraph([registry.create_instance("plugin-scale", "scale")])
    if published_input:
        graph.add_input("number", "scale", "value", registry)
    else:
        graph.add_node(registry.create_instance("set-int", "source", parameters={"value": 7}))
        graph.add_edge(WorkflowEdge("source", "value", "scale", "value"), registry)
    graph.add_output("scaled", "scale", "result", registry)
    return graph


def test_registry_plugins_are_local_and_imported_once(plugin):
    import_path = list(sys.path)
    first = create_node_registry(plugins=[plugin])
    second = create_node_registry(plugins=[plugin])
    assert first.require("plugin-scale") is second.require("plugin-scale")
    assert create_node_registry().get("plugin-scale") is None
    assert first.require("set-int")
    assert sys.path == import_path
    groups = load_plugin_groups([plugin])
    assert groups[0].node_definitions == (first.require("plugin-scale"),)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("", "AVAILABLE_NODES"),
        ("AVAILABLE_NODES = None", "TypeError"),
        ("AVAILABLE_NODES = [42]", "NodeDefinition"),
        ("raise RuntimeError('broken plugin')", "broken plugin"),
        ("import flowgraph_nonexistent_plugin_dependency", "ModuleNotFoundError"),
        ("def invalid syntax", "SyntaxError"),
        ("raise SystemExit(4)", "SystemExit"),
    ],
)
def test_plugin_errors_identify_file_and_allow_retry(tmp_path, source, message):
    path = tmp_path / "bad.py"
    path.write_text(source, encoding="utf-8")
    with pytest.raises(PluginError, match=message) as caught:
        create_node_registry(plugins=[path])
    assert str(path) in str(caught.value)
    path.write_text(PLUGIN_SOURCE, encoding="utf-8")
    assert create_node_registry(plugins=[path]).require("plugin-scale")


def test_invalid_paths_and_duplicate_files_are_rejected(tmp_path, plugin, monkeypatch):
    for path in (tmp_path / "missing.py", tmp_path, tmp_path / "nodes.txt"):
        with pytest.raises(PluginError, match="existing Python"):
            create_node_registry(plugins=[path])
    monkeypatch.chdir(tmp_path)
    assert resolve_plugin_paths([plugin.name]) == (plugin,)
    with pytest.raises(PluginError, match="more than once"):
        create_node_registry(plugins=[plugin, plugin.name])


def test_duplicate_node_ids_across_plugins_and_builtins_are_rejected(tmp_path, plugin):
    duplicate = tmp_path / "duplicate.py"
    duplicate.write_text(PLUGIN_SOURCE, encoding="utf-8")
    with pytest.raises(PluginError, match="duplicate.py.*already registered"):
        create_node_registry(plugins=[plugin, duplicate])
    duplicate.write_text(
        "from flowgraph.adapters.simple_sources import SET_INT\nAVAILABLE_NODES = (SET_INT,)\n",
        encoding="utf-8",
    )
    # A different file ensures this checks a fresh module, not a cached import.
    builtin = tmp_path / "builtin.py"
    builtin.write_text(duplicate.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(PluginError, match="builtin.py.*already registered"):
        create_node_registry(plugins=[builtin])


def test_multiple_same_named_plugins_load_in_order(tmp_path, plugin):
    other = tmp_path / "other" / plugin.name
    other.parent.mkdir()
    other.write_text(PLUGIN_SOURCE.replace("plugin-scale", "plugin-other"), encoding="utf-8")
    registry = create_node_registry(plugins=[other, plugin])
    assert list(registry.definitions)[-2:] == ["plugin-other", "plugin-scale"]


def test_iterable_exports_are_reusable_and_empty_exports_are_valid(plugin, tmp_path):
    plugin.write_text(
        PLUGIN_SOURCE + "\nAVAILABLE_NODES = iter(AVAILABLE_NODES)\n", encoding="utf-8"
    )
    first = create_node_registry(plugins=[plugin])
    second = create_node_registry(plugins=[plugin])
    assert first.require("plugin-scale") is second.require("plugin-scale")
    empty = tmp_path / "empty.py"
    empty.write_text("AVAILABLE_NODES = ()", encoding="utf-8")
    assert load_plugin_groups([empty])[0].node_definitions == ()


def test_cli_plugin_inputs_overrides_inspection_and_saved_json(plugin, tmp_path, capsys):
    registry = create_node_registry(plugins=[plugin])
    path = save_workflow(
        plugin_workflow(registry, published_input=True), tmp_path / "workflow.json"
    )
    original = path.read_text(encoding="utf-8")
    args = [str(path), "--plugin", str(plugin), "-i", "number=7", "--override", "scale.factor=3"]
    assert main(["inspect", *args, "--full"]) == 0
    output = capsys.readouterr().out
    assert "Plugin Scale" in output and "factor" in output
    assert main(["run", *args]) == 0
    assert "scaled: 21" in capsys.readouterr().out
    graph, result = execute_cli_workflow(path, plugins=[plugin], inputs={"number": 4})
    assert workflow_outputs(graph, result) == {"scaled": 8}
    assert "Plugin Scale" in inspect_workflow(path, plugins=[plugin], full=True)
    assert path.read_text(encoding="utf-8") == original
    assert main(["run", str(path)]) == 2
    assert "unknown definition 'plugin-scale'" in capsys.readouterr().err


def test_cli_errors_and_repeatable_plugin_flags(plugin, tmp_path, capsys):
    other = tmp_path / "other.py"
    other.write_text("AVAILABLE_NODES = ()", encoding="utf-8")
    registry = create_node_registry(plugins=[plugin])
    path = save_workflow(plugin_workflow(registry), tmp_path / "workflow.json")
    assert main(["run", str(path), "--plugin", str(other), "--plugin", str(plugin)]) == 0
    assert "scaled: 14" in capsys.readouterr().out
    assert main(["run", str(path), "--plugin", str(tmp_path / "missing.py")]) == 2
    assert "missing.py" in capsys.readouterr().err
    assert (
        main(
            [
                "serve",
                "--workspace",
                str(tmp_path),
                "--plugin",
                str(plugin),
                "--plugin",
                str(plugin),
            ]
        )
        == 2
    )
    assert "more than once" in capsys.readouterr().err


def test_real_cli_process_loads_plugin(plugin, tmp_path):
    registry = create_node_registry(plugins=[plugin])
    path = save_workflow(plugin_workflow(registry), tmp_path / "workflow.json")
    completed = subprocess.run(
        [sys.executable, "-m", "flowgraph", "run", str(path), "--plugin", str(plugin)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "scaled: 14" in completed.stdout


def test_explicit_execution_registry_does_not_change_default_registry(plugin):
    registry = create_node_registry(plugins=[plugin])
    document = json.dumps(workflow_to_dict(plugin_workflow(registry)))
    result = json.loads(execute_workflow_json(document, registry=registry))
    assert result["status"] == "ok" and result["outputs"] == {"scaled": 14}
    assert json.loads(execute_workflow_json(document))["status"] == "error"


def test_server_catalog_and_both_worker_modes_use_startup_plugins(plugin, tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = create_node_registry(plugins=[plugin])
    document = workflow_to_dict(plugin_workflow(registry))
    monkeypatch.chdir(tmp_path)
    with LocalServer(workspace, port=0, plugins=[plugin.name], execution_timeout=15) as server:
        assert server.plugins == (plugin,)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            status, catalog = request(server, "GET", "/api/v1/catalog")
            assert status == 200
            node = catalog["groups"][-1]["nodes"][0]
            assert node["id"] == "plugin-scale" and "executor" not in node
            for options in (None, {"session_id": "plugin-test"}, {"session_id": "plugin-test"}):
                body = {"workflow": document}
                if options is not None:
                    body["options"] = options
                status, submitted = request(server, "POST", "/api/v1/executions", body)
                assert status == 202
                job = wait_job(server, submitted["id"])
                assert job["state"] == "completed", job
                assert job["result"]["outputs"] == {"scaled": 14}
            assert job["result"]["execution_order"] == []
        finally:
            server.shutdown()
            thread.join(timeout=5)
            assert not thread.is_alive()
    with LocalServer(workspace, port=0) as plain:
        assert all(
            group["label"] != catalog["groups"][-1]["label"] for group in plain.catalog["groups"]
        )


def test_server_rejects_bad_plugin_before_binding(tmp_path):
    path = tmp_path / "bad.py"
    path.write_text("AVAILABLE_NODES = [None]", encoding="utf-8")
    with pytest.raises(PluginError, match="bad.py"):
        LocalServer(tmp_path, port=0, plugins=[path])


def test_documented_plugin_example_executes(tmp_path):
    guide = (Path(__file__).parents[1] / "doc" / "user-guide" / "custom-nodes.md").read_text(
        encoding="utf-8"
    )
    section = guide.split("## Load Python-file plugins from the CLI or server", 1)[1]
    source = section.split("```python\n", 1)[1].split("\n```", 1)[0]
    path = tmp_path / "custom_nodes.py"
    path.write_text(source, encoding="utf-8")
    registry = create_node_registry(plugins=[path])
    graph = WorkflowGraph([registry.create_instance("scale-integer", "scale")])
    graph.add_input("number", "scale", "value", registry)
    graph.add_output("scaled", "scale", "result", registry)
    workflow = save_workflow(graph, tmp_path / "scaled-workflow.json")
    loaded, result = execute_cli_workflow(workflow, plugins=[path], inputs={"number": 7})
    assert workflow_outputs(loaded, result) == {"scaled": 14}
