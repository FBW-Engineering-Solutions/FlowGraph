"""Transfer Fields exposes and applies Muscat's inside/outside transfer modes."""

import numpy as np
import pytest
from Muscat.MeshContainers import ElementsDescription as ED
from Muscat.MeshContainers.Mesh import Mesh

from flowgraph.adapters import field_ops
from flowgraph.adapters.field_ops import TRANSFER_FIELDS_NODE
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import WorkflowGraph
from flowgraph.application.workflow_io import load_workflow, save_workflow
from flowgraph.domain.mesh_document import MeshDocument

METHODS = ("Interp/Clamp", "Interp/Nearest", "Interp/Extrap", "Interp/ZeroFill")


def tetrahedron():
    mesh = Mesh()
    mesh.SetNodes(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        generateOriginalIDs=True,
    )
    mesh.GetElementsOfType(ED.Tetrahedron_4).AddNewElements(np.array([[0, 1, 2, 3]]), np.array([0]))
    mesh.nodeFields["temperature"] = np.array([0.0, 1.0, 2.0, 3.0])
    mesh.elemFields["material"] = np.array([7.0])
    mesh.nodesTags.CreateTag("all").SetIds([0, 1, 2, 3])
    mesh.AddElementsToTag([0], "volume")
    return MeshDocument(mesh)


def test_interpolation_is_ui_only_and_defaults_to_clamp():
    definition = next(p for p in TRANSFER_FIELDS_NODE.parameters if p.name == "method")
    assert definition.default == "Interp/Clamp"
    assert tuple(option.value for option in definition.options) == METHODS
    assert [port.name for port in TRANSFER_FIELDS_NODE.inputs] == ["source_data", "target"]
    assert TRANSFER_FIELDS_NODE.create_instance("transfer").parameters["method"] == "Interp/Clamp"


@pytest.mark.parametrize("method", [None, *METHODS])
@pytest.mark.parametrize("tags_only", [False, True])
def test_method_reaches_both_transfer_operators(monkeypatch, method, tags_only):
    source, target = tetrahedron(), tetrahedron()
    calls = []

    def transfer_operator(field, points, *, method, **kwargs):
        calls.append(method)
        return np.eye(len(points)), None, None

    monkeypatch.setattr(field_ops, "GetFieldTransferOp", transfer_operator)
    parameters = {
        "transferNodeData": not tags_only,
        "transferElementData": not tags_only,
        "transferNodeTags": tags_only,
        "transferElementTags": tags_only,
    }
    if method is not None:
        parameters["method"] = method
    result = TRANSFER_FIELDS_NODE.executor({"source_data": source, "target": target}, parameters)[
        "mesh_document"
    ]
    assert calls == [method or "Interp/Clamp"] * 2
    assert np.shares_memory(result.mesh.nodes, target.mesh.nodes)


@pytest.mark.parametrize(
    "method,expected",
    [
        (None, [1.2, 1.0]),
        ("Interp/Clamp", [1.2, 1.0]),
        ("Interp/Extrap", [1.2, 0.8]),
        ("Interp/ZeroFill", [1.2, 0.0]),
        ("Interp/Nearest", [1.2, 0.0]),
        ("Nearest/Nearest", [0.0, 0.0]),
    ],
)
def test_real_nodal_interpolation_inside_and_outside(method, expected):
    source = tetrahedron()
    target = Mesh()
    target.SetNodes([[0.2, 0.2, 0.2], [-0.2, 0.2, 0.2]], generateOriginalIDs=True)
    target = MeshDocument(target)
    parameters = {
        "transferElementData": False,
        "transferNodeTags": False,
        "transferElementTags": False,
    }
    if method is not None:
        parameters["method"] = method
    result = TRANSFER_FIELDS_NODE.executor({"source_data": source, "target": target}, parameters)[
        "mesh_document"
    ]
    np.testing.assert_allclose(result.mesh.nodeFields["temperature"], expected, atol=1e-10)
    assert "temperature" not in target.mesh.nodeFields
    np.testing.assert_array_equal(source.mesh.nodeFields["temperature"], [0.0, 1.0, 2.0, 3.0])


@pytest.mark.parametrize("method", METHODS)
def test_real_element_and_tag_transfer(method):
    source, target = tetrahedron(), tetrahedron()
    target.mesh.nodeFields.pop("temperature")
    target.mesh.elemFields.pop("material")
    result = TRANSFER_FIELDS_NODE.executor(
        {"source_data": source, "target": target},
        {"method": method, "transferNodeTags": True, "transferElementTags": True},
    )["mesh_document"]
    np.testing.assert_allclose(result.mesh.nodeFields["temperature"], [0.0, 1.0, 2.0, 3.0])
    np.testing.assert_allclose(result.mesh.elemFields["material"], [7.0])
    np.testing.assert_array_equal(result.mesh.nodesTags["all"].GetIds(), [0, 1, 2, 3])
    np.testing.assert_array_equal(result.mesh.GetElementsInTag("volume"), [0])
    assert "temperature" not in target.mesh.nodeFields
    assert "material" not in target.mesh.elemFields


@pytest.mark.parametrize("method", METHODS)
def test_interpolation_selection_round_trips(tmp_path, method):
    graph = WorkflowGraph(
        [TRANSFER_FIELDS_NODE.create_instance("transfer", parameters={"method": method})]
    )
    path = tmp_path / "transfer.json"
    save_workflow(graph, path)
    restored = load_workflow(path, create_node_registry())
    assert restored.require_node("transfer").parameters["method"] == method
