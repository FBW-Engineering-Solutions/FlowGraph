"""Tests for the JSON boundary used by the browser WASM executor."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from Muscat.MeshTools.MeshCreationTools import CreateCube, CreateSquare
from PIL import Image as PillowImage

from flowgraph.adapters.simple_sources import SET_STRING
from flowgraph.adapters.workflow_interfaces import WORKFLOW_OUTPUT
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.wasm_execution import _display_meshes, execute_workflow_json
from flowgraph.application.workflow_core import WorkflowEdge, WorkflowGraph
from flowgraph.application.workflow_io import workflow_to_dict


def _workflow_json() -> str:
    registry = create_node_registry()
    workflow = WorkflowGraph(
        [
            SET_STRING.create_instance("source", parameters={"value": "hello"}),
            WORKFLOW_OUTPUT.create_instance("output", parameters={"name": "result"}),
        ]
    )
    workflow.add_edge(WorkflowEdge("source", "value", "output", "value"), registry)
    workflow.sync_boundary_nodes(registry)
    return json.dumps(workflow_to_dict(workflow))


def _show_value_workflow_json() -> str:
    registry = create_node_registry()
    workflow = WorkflowGraph(
        [
            SET_STRING.create_instance("source", parameters={"value": "hello"}),
            registry.create_instance("show-value", "display"),
        ]
    )
    workflow.add_edge(WorkflowEdge("source", "value", "display", "value"), registry)
    return json.dumps(workflow_to_dict(workflow))


def _show_image_workflow_json(path: str) -> str:
    registry = create_node_registry()
    workflow = WorkflowGraph(
        [
            registry.create_instance("read-image", "source", parameters={"path": path}),
            registry.create_instance("local-view", "display"),
        ]
    )
    workflow.add_edge(WorkflowEdge("source", "image", "display", "input"), registry)
    return json.dumps(workflow_to_dict(workflow))


def test_execute_workflow_json_returns_python_generated_projection_and_results() -> None:
    response = json.loads(execute_workflow_json(_workflow_json()))

    assert response["status"] == "ok"
    assert response["execution_order"] == ["source", "output"]
    assert response["outputs"] == {"result": "hello"}
    assert response["nodes"]["outputs"]["source"] == {"value": "hello"}
    assert response["display_inputs"]["output"]["value"] == "hello"
    assert response["nodes"]["inputs"]["output"] == {"value": "hello"}
    assert "Workflow:" in response["projection"]
    assert "[source] String Input" in response["projection"]


def test_execute_workflow_json_returns_show_value_input_as_python_text() -> None:
    response = json.loads(execute_workflow_json(_show_value_workflow_json()))

    assert response["status"] == "ok"
    assert response["nodes"]["inputs"]["display"]["value"] == "hello"
    assert response["display_inputs"]["display"]["value"] == "hello"


def test_execute_workflow_json_returns_png_preview_for_show_image() -> None:
    with TemporaryDirectory() as directory:
        image_path = Path(directory) / "input.png"
        PillowImage.new("RGBA", (3, 2), (12, 34, 56, 78)).save(image_path)

        response = json.loads(execute_workflow_json(_show_image_workflow_json(str(image_path))))

    assert response["status"] == "ok"
    preview = response["display_images"]["display"]["input"]
    assert preview["mime_type"] == "image/png"
    assert preview["width"] == 3
    assert preview["height"] == 2
    assert preview["mode"] == "RGBA"
    assert preview["data"].startswith("iVBOR")


def test_display_meshes_projects_surface_without_changing_the_input() -> None:
    from flowgraph.domain.mesh_document import MeshDocument

    mesh = CreateCube(dimensions=[3, 3, 3])
    mesh.nodeFields["temperature"] = np.arange(mesh.GetNumberOfNodes(), dtype=float)
    mesh.nodeFields["velocity"] = np.tile([3.0, 4.0, 0.0], (mesh.GetNumberOfNodes(), 1))
    original_count = mesh.GetNumberOfElements()
    document = MeshDocument(mesh)
    registry = create_node_registry()
    workflow = WorkflowGraph([registry.create_instance("mesh-sink", "view")])

    preview = _display_meshes(workflow, {"view": {"mesh": document}})["view"]

    assert len(preview["i"]) == len(preview["j"]) == len(preview["k"]) > 0
    assert len(preview["x"]) == len(preview["y"]) == len(preview["z"])
    assert all(
        0 <= index < len(preview["x"]) for index in preview["i"] + preview["j"] + preview["k"]
    )
    assert sorted(preview["fields"]["temperature"]) == list(range(mesh.GetNumberOfNodes()))
    assert preview["fields"]["velocity"] == [5.0] * len(preview["x"])
    assert "flowgraph_node_id" not in preview["fields"]
    assert mesh.GetNumberOfElements() == original_count
    assert "temperature" in mesh.nodeFields


def test_display_meshes_handles_planar_mesh_and_skips_other_nodes() -> None:
    from flowgraph.domain.mesh_document import MeshDocument

    registry = create_node_registry()
    workflow = WorkflowGraph(
        [
            registry.create_instance("mesh-sink", "view"),
            registry.create_instance("show-value", "other"),
        ]
    )
    document = MeshDocument(CreateSquare(dimensions=[2, 2]))

    previews = _display_meshes(
        workflow,
        {
            "view": {"mesh": document},
            "other": {"value": document},
        },
    )

    assert len(previews["view"]["i"]) == 2
    assert previews["view"]["z"] == [0.0] * 4
    assert "other" not in previews


def test_execute_workflow_json_returns_mesh_preview_for_sink() -> None:
    registry = create_node_registry()
    workflow = WorkflowGraph(
        [
            registry.create_instance("create-square", "source"),
            registry.create_instance("mesh-sink", "view"),
        ]
    )
    workflow.add_edge(WorkflowEdge("source", "mesh", "view", "mesh"), registry)

    response = json.loads(execute_workflow_json(json.dumps(workflow_to_dict(workflow))))

    assert response["status"] == "ok"
    assert len(response["display_meshes"]["view"]["i"]) == 2
    assert response["nodes"]["inputs"]["view"]["mesh"]["type"] == "MeshDocument"


def test_execute_workflow_json_serializes_invalid_requests_as_errors() -> None:
    response = json.loads(execute_workflow_json("not-json"))

    assert response["status"] == "error"
    assert response["error"]["type"] == "WorkflowPersistenceError"
    assert "not valid JSON" in response["error"]["message"]


def test_wasm_execution_uses_the_complete_core_node_registry() -> None:
    registry = create_node_registry()

    assert registry.get("create-cube") is not None
    assert registry.get("convert-mesh-file-format") is not None
    assert registry.get("local-view") is not None
    assert registry.get("show-value") is not None
    assert registry.get("download-url") is not None
    assert registry.get("mesh-sink") is not None
    assert registry.get("load-meshio") is not None
    assert registry.get("cosapp-workflow") is not None


def test_wasm_execution_module_uses_the_core_node_registry() -> None:
    source = (
        Path(__file__).parents[1] / "src" / "flowgraph" / "application" / "wasm_execution.py"
    ).read_text(encoding="utf-8")

    assert "from flowgraph.application.node_registry import create_node_registry" in source
