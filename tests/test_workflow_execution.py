"""Tests for the transport-independent JSON workflow execution boundary."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pytest
from Muscat.MeshTools.MeshCreationTools import CreateCube, CreateSquare
from PIL import Image as PillowImage

from flowgraph.adapters.simple_sources import SET_STRING
from flowgraph.adapters.workflow_interfaces import WORKFLOW_INPUT, WORKFLOW_OUTPUT
from flowgraph.application import workflow_execution
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import (
    NodeDefinition,
    NodeExecutionError,
    WorkflowEdge,
    WorkflowGraph,
    WorkflowRunResult,
)
from flowgraph.application.workflow_execution import _display_meshes, execute_workflow_json
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


@pytest.mark.parametrize("failed", [False, True])
def test_execution_serializes_nonfinite_values_as_null(monkeypatch, failed):
    values = {
        "mean": float("nan"),
        "std": float("inf"),
        "nested": [float("-inf"), np.float32("nan"), np.float64("inf"), 1.5],
        "text": "NaN and Infinity are text",
        "flag": False,
    }
    result = WorkflowRunResult(
        execution_order=("source", "output"),
        node_outputs={"source": {"value": values}, "output": {"value": values}},
        node_inputs={"output": {"value": values}},
    )

    def run(*args, **kwargs):
        if failed:
            raise NodeExecutionError("output", "workflow-output", "failed", partial_result=result)
        return result

    monkeypatch.setattr(workflow_execution.WorkflowExecutor, "run", run)
    monkeypatch.setattr(
        workflow_execution, "_display_meshes", lambda *args: {"preview": {"values": values}}
    )

    def reject_constant(value):
        raise AssertionError(f"Non-standard JSON constant: {value}")

    response = json.loads(execute_workflow_json(_workflow_json()), parse_constant=reject_constant)
    expected = {
        "mean": None,
        "std": None,
        "nested": [None, None, None, 1.5],
        "text": "NaN and Infinity are text",
        "flag": False,
    }
    retained = response["partial"] if failed else response["nodes"]
    assert retained["outputs"]["source"]["value"] == expected
    assert retained["inputs"]["output"]["value"] == expected
    if failed:
        assert response["status"] == "error"
        assert response["error"]["node_id"] == "output"
    else:
        assert response["status"] == "ok"
        assert response["outputs"] == {"result": expected}
        assert response["display_meshes"]["preview"]["values"] == expected
        assert "nan" in response["display_inputs"]["output"]["value"]


def _public_input_workflow(definition_id="set-string", value="saved"):
    registry = create_node_registry()
    workflow = WorkflowGraph(
        [
            WORKFLOW_INPUT.create_instance("input", parameters={"name": "value"}),
            registry.create_instance(definition_id, "target", parameters={"value": value}),
            WORKFLOW_OUTPUT.create_instance("output", parameters={"name": "result"}),
        ]
    )
    workflow.add_edge(WorkflowEdge("input", "value", "target", "value"), registry)
    workflow.add_edge(WorkflowEdge("target", "value", "output", "value"), registry)
    workflow.sync_boundary_nodes(registry)
    return workflow


@pytest.mark.parametrize(
    ("definition_id", "value"),
    [("set-string", "saved"), ("set-string", ""), ("set-int", 0), ("set-boolean", False)],
)
def test_execution_uses_saved_public_input_and_returns_warning(definition_id, value):
    workflow = _public_input_workflow(definition_id, value)
    response = json.loads(execute_workflow_json(json.dumps(workflow_to_dict(workflow))))

    assert response["status"] == "ok"
    assert response["outputs"] == {"result": value}
    assert response["nodes"]["inputs"]["target"]["value"] == value
    assert len(response["warnings"]) == 1
    assert "Workflow input 'value' was not provided" in response["warnings"][0]
    assert "saved parameter value" in response["warnings"][0]
    assert "target.value" in response["warnings"][0]


def test_execution_rejects_missing_public_input_without_saved_parameter():
    registry = create_node_registry()
    workflow = WorkflowGraph(
        [
            WORKFLOW_INPUT.create_instance("input", parameters={"name": "value"}),
            registry.create_instance("show-value", "display"),
        ]
    )
    workflow.add_edge(WorkflowEdge("input", "value", "display", "value"), registry)
    workflow.sync_boundary_nodes(registry)

    response = json.loads(execute_workflow_json(json.dumps(workflow_to_dict(workflow))))

    assert response["status"] == "error"
    assert "Missing required workflow inputs: value" in response["error"]["message"]
    assert response["warnings"] == []


def test_execution_rejects_conflicting_saved_public_inputs():
    registry = create_node_registry()
    workflow = _public_input_workflow()
    workflow.add_node(
        registry.create_instance("set-string", "other", parameters={"value": "different"})
    )
    workflow.add_edge(WorkflowEdge("input", "value", "other", "value"), registry)
    workflow.sync_boundary_nodes(registry)

    response = json.loads(execute_workflow_json(json.dumps(workflow_to_dict(workflow))))

    assert response["status"] == "error"
    assert "Conflicting saved parameter values" in response["error"]["message"]
    assert response["warnings"] == []


@pytest.mark.parametrize("value", ["", 0, False])
def test_shared_input_resolver_preserves_explicit_values(value):
    from flowgraph.application.workflow_cli import resolve_workflow_inputs

    definition_id = (
        "set-string"
        if isinstance(value, str)
        else "set-boolean"
        if isinstance(value, bool)
        else "set-int"
    )
    workflow = _public_input_workflow(definition_id, value)
    warnings = []

    injected = resolve_workflow_inputs(workflow, {"value": value}, on_warning=warnings.append)

    assert injected == {"input": {"value": value}}
    assert warnings == []


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
    assert preview["field_components"]["velocity"] == [[3.0, 4.0, 0.0]] * len(preview["x"])
    assert "temperature" not in preview["field_components"]
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


def test_display_meshes_preserves_element_fields_when_triangulating() -> None:
    from flowgraph.domain.mesh_document import MeshDocument

    mesh = CreateSquare(dimensions=[3, 2])
    # CreateSquare also includes six boundary bars before its two quadrangles.
    material = np.array([-1.0] * 6 + [7.0, 19.0])
    mesh.elemFields["material"] = material.copy()
    vectors = np.column_stack((material, material * 2, np.zeros(len(material))))
    mesh.elemFields["velocity"] = vectors.copy()
    document = MeshDocument(mesh)
    registry = create_node_registry()
    workflow = WorkflowGraph([registry.create_instance("mesh-sink", "view")])
    preview = _display_meshes(workflow, {"view": {"mesh": document}})["view"]
    assert sorted(preview["cell_fields"]["material"]) == [7.0, 7.0, 19.0, 19.0]
    assert len(preview["cell_fields"]["flowgraph_element_id"]) == len(preview["i"])
    assert sorted(preview["cell_field_components"]["velocity"]) == [
        [7.0, 14.0, 0.0],
        [7.0, 14.0, 0.0],
        [19.0, 38.0, 0.0],
        [19.0, 38.0, 0.0],
    ]
    np.testing.assert_allclose(
        sorted(preview["cell_fields"]["velocity"]), np.sqrt(5) * np.array([7, 7, 19, 19])
    )
    np.testing.assert_array_equal(mesh.elemFields["material"], material)
    np.testing.assert_array_equal(mesh.elemFields["velocity"], vectors)


def test_display_meshes_maps_volume_fields_to_new_boundary_faces() -> None:
    from Muscat.MeshContainers import ElementsDescription as ED

    from flowgraph.domain.mesh_document import MeshDocument

    mesh = CreateCube(dimensions=[2, 2, 2], ofTetras=True)
    # Remove explicit boundary triangles to exercise generated skin ownership.
    del mesh.elements[ED.ElementType.Triangle_3]
    mesh.elemFields["material"] = np.full(mesh.GetNumberOfElements(), 42.0)
    mesh.elemFields["invalid"] = np.full(mesh.GetNumberOfElements(), np.nan)
    mesh.elemFields["velocity"] = np.tile([3.0, 4.0], (mesh.GetNumberOfElements(), 1))
    document = MeshDocument(mesh)
    registry = create_node_registry()
    workflow = WorkflowGraph([registry.create_instance("mesh-sink", "view")])
    preview = _display_meshes(workflow, {"view": {"mesh": document}})["view"]
    assert preview["cell_fields"]["material"] == [42.0] * len(preview["i"])
    assert "invalid" not in preview["cell_fields"]
    assert preview["cell_fields"]["velocity"] == [5.0] * len(preview["i"])
    assert preview["cell_field_components"]["velocity"] == [[3.0, 4.0]] * len(preview["i"])
    assert mesh.GetNumberOfElements() == 6


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
    assert "WASM" not in response["error"]["message"]


def test_execution_reuses_registry_without_retaining_previous_workflow(monkeypatch) -> None:
    registries = []

    def registry_factory():
        registry = create_node_registry()
        registries.append(registry)
        return registry

    monkeypatch.setattr(workflow_execution, "_REGISTRY", None)
    monkeypatch.setattr(workflow_execution, "create_node_registry", registry_factory)
    first = json.loads(execute_workflow_json(_workflow_json()))
    invalid = json.loads(execute_workflow_json("not-json"))
    second = json.loads(execute_workflow_json(_show_value_workflow_json()))

    assert len(registries) == 1
    assert first["outputs"] == {"result": "hello"}
    assert invalid["status"] == "error"
    assert second["status"] == "ok"
    assert second["outputs"] == {}
    assert set(second["nodes"]["outputs"]) == {"source", "display"}


def test_wasm_specific_module_is_removed() -> None:
    application = Path(workflow_execution.__file__).parent
    assert not (application / "wasm_execution.py").exists()


def test_execute_workflow_json_reports_failing_node_and_original_line(monkeypatch) -> None:
    def failing_node(_inputs, _parameters):
        raise ValueError("dimension mismatch")

    registry = create_node_registry()
    registry.register(
        NodeDefinition(
            id="failing-test-node",
            icon="",
            label="Failing Test Node",
            ports=(),
            executor=failing_node,
        )
    )
    workflow = WorkflowGraph([registry.create_instance("failing-test-node", "transfer-fields-13")])
    monkeypatch.setattr(workflow_execution, "_REGISTRY", registry)
    response = json.loads(execute_workflow_json(json.dumps(workflow_to_dict(workflow))))

    assert response["status"] == "error"
    detail = response["error"]
    assert detail["type"] == "NodeExecutionError"
    assert detail["node_id"] == "transfer-fields-13"
    assert detail["definition_id"] == "failing-test-node"
    assert "dimension mismatch" in detail["message"]
    assert 'raise ValueError("dimension mismatch")' in detail["traceback"]
    assert "test_workflow_execution.py" in detail["traceback"]
    assert "ValueError: dimension mismatch" in detail["traceback"]
    assert "The above exception was the direct cause" in detail["traceback"]


def test_workflow_execution_uses_the_complete_core_node_registry() -> None:
    registry = create_node_registry()

    assert registry.get("create-cube") is not None
    assert registry.get("convert-mesh-file-format") is not None
    assert registry.get("local-view") is not None
    assert registry.get("show-value") is not None
    assert registry.get("download-url") is not None
    assert registry.get("mesh-sink") is not None
    assert registry.get("load-meshio") is not None
    assert registry.get("cosapp-workflow") is not None


def test_workflow_execution_module_uses_the_core_node_registry() -> None:
    source = (
        Path(__file__).parents[1] / "src" / "flowgraph" / "application" / "workflow_execution.py"
    ).read_text(encoding="utf-8")

    assert "from flowgraph.application.node_registry import create_node_registry" in source
