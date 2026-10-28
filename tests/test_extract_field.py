"""Named nodal and element field extraction."""

import numpy as np
import pytest
from Muscat.MeshContainers.Mesh import Mesh

from flowgraph.adapters import ADAPTERS
from flowgraph.adapters.data_types import ANY, MESH_DOCUMENT
from flowgraph.adapters.field_ops import EXTRACT_FIELD_NODE
from flowgraph.adapters.mesh_creation_tools import CREATE_CUBE_NODE
from flowgraph.adapters.simple_sources import SET_STRING
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import WorkflowEdge, WorkflowExecutor, WorkflowGraph
from flowgraph.application.workflow_io import load_workflow, save_workflow
from flowgraph.domain.mesh_document import MeshDocument


def test_extract_field_registered_under_field_ops() -> None:
    mesh_tools = next(group for group in ADAPTERS.groups if group.label == "Mesh Tools")
    field_ops = next(group for group in mesh_tools.subgroups if group.label == "Field Ops")
    assert EXTRACT_FIELD_NODE in field_ops.node_definitions
    assert ADAPTERS.require("extract-field") is EXTRACT_FIELD_NODE
    assert EXTRACT_FIELD_NODE.input("mesh").data_type is MESH_DOCUMENT
    assert EXTRACT_FIELD_NODE.output("field").data_type is ANY
    assert [port.name for port in EXTRACT_FIELD_NODE.inputs] == ["mesh", "entity", "fieldName"]


@pytest.mark.parametrize("entity", ["node", "element"])
@pytest.mark.parametrize(
    "values",
    [
        np.array([1.5, 2.5]),
        np.arange(6, dtype=np.int32).reshape(2, 3),
        np.arange(18.0).reshape(2, 3, 3),
        np.array(["first", "second"]),
        np.empty((0, 3)),
    ],
)
def test_extract_field_preserves_values_dtype_shape_and_isolation(entity, values) -> None:
    source = MeshDocument(Mesh())
    fields = source.mesh.nodeFields if entity == "node" else source.mesh.elemFields
    fields["data"] = values.copy()
    # The association must disambiguate identical names in both dictionaries.
    other = source.mesh.elemFields if entity == "node" else source.mesh.nodeFields
    other["data"] = np.array([-100])
    result = EXTRACT_FIELD_NODE.executor({"mesh": source}, {"entity": entity, "fieldName": "data"})[
        "field"
    ]
    np.testing.assert_array_equal(result, values)
    assert result.dtype == values.dtype
    assert result.shape == values.shape
    assert not np.shares_memory(result, fields["data"])
    if result.size:
        result.flat[0] = result.flat[-1]
    np.testing.assert_array_equal(fields["data"], values)


@pytest.mark.parametrize(
    "parameters,message",
    [
        ({}, "nonempty"),
        ({"fieldName": "   "}, "nonempty"),
        ({"fieldName": 42}, "nonempty"),
        ({"entity": "cell", "fieldName": "data"}, "association"),
        ({"entity": "node", "fieldName": "missing"}, "Node field 'missing'.*available"),
        ({"entity": "element", "fieldName": "missing"}, "Element field 'missing'.*available"),
    ],
)
def test_invalid_field_selection_has_clear_error(parameters, message) -> None:
    with pytest.raises(ValueError, match=message):
        EXTRACT_FIELD_NODE.executor({"mesh": MeshDocument(Mesh())}, parameters)


@pytest.mark.parametrize(
    "entity,field_name",
    [
        ("node", "flowgraph_node_id"),
        ("element", "flowgraph_element_id"),
    ],
)
def test_connected_field_selection_round_trips_and_executes(tmp_path, entity, field_name) -> None:
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            CREATE_CUBE_NODE.create_instance("mesh"),
            SET_STRING.create_instance("name", parameters={"value": field_name}),
            SET_STRING.create_instance("association", parameters={"value": entity}),
            EXTRACT_FIELD_NODE.create_instance("extract", parameters={"fieldName": "overridden"}),
        ]
    )
    for edge in (
        WorkflowEdge("mesh", "mesh", "extract", "mesh"),
        WorkflowEdge("name", "value", "extract", "fieldName"),
        WorkflowEdge("association", "value", "extract", "entity"),
    ):
        graph.add_edge(edge, registry)
    path = tmp_path / "extract.json"
    save_workflow(graph, path)
    restored = load_workflow(path, registry)
    result = WorkflowExecutor(registry).run(restored)
    mesh = result.node_outputs["mesh"]["mesh"].mesh
    fields = mesh.nodeFields if entity == "node" else mesh.elemFields
    np.testing.assert_array_equal(result.node_outputs["extract"]["field"], fields[field_name])
    assert restored.require_node("extract").parameters["fieldName"] == field_name
