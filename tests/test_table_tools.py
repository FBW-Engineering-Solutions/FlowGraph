import numpy as np
import pytest
from Muscat.MeshContainers import ElementsDescription as ED
from Muscat.MeshContainers.Mesh import Mesh

from flowgraph.adapters import ADAPTERS
from flowgraph.adapters.data_types import LIST_FLOAT, LIST_INT, MESH_DOCUMENT, TABLE_DOCUMENT
from flowgraph.adapters.table_tools import AGGREGATE_LISTS_TO_TABLE, MESH_TO_TABLE
from flowgraph.application.workflow_core import (
    NodeDefinition,
    NodeInstance,
    NodeRegistry,
    PortDefinition,
    PortDirection,
    WorkflowEdge,
    WorkflowExecutor,
    WorkflowGraph,
)
from flowgraph.domain.mesh_document import MeshDocument


def _source_definition() -> NodeDefinition:
    return NodeDefinition(
        id="vectors",
        icon="",
        label="Vectors",
        ports=(
            PortDefinition("temperature", PortDirection.OUTPUT, LIST_FLOAT),
            PortDefinition("pressure", PortDirection.OUTPUT, LIST_INT),
        ),
        executor=lambda _inputs, _parameters: {
            "temperature": [20.0, 21.5],
            "pressure": [100, 101],
        },
    )


def _registry(*definitions: NodeDefinition) -> NodeRegistry:
    registry = NodeRegistry()
    for definition in definitions:
        registry.register(definition)
    return registry


def test_aggregate_lists_to_table_uses_source_output_names_as_columns() -> None:
    source = _source_definition()
    registry = _registry(source, AGGREGATE_LISTS_TO_TABLE)
    graph = WorkflowGraph(
        [NodeInstance("vectors", source.id), NodeInstance("table", AGGREGATE_LISTS_TO_TABLE.id)]
    )
    graph.add_edge(WorkflowEdge("vectors", "temperature", "table", "column_1"), registry)
    graph.add_edge(WorkflowEdge("vectors", "pressure", "table", "column_2"), registry)

    result = WorkflowExecutor(registry).run(graph)

    assert AGGREGATE_LISTS_TO_TABLE.icon == "mdi-file-table-outline"
    assert result.node_outputs["table"] == {
        "table": {"temperature": [20.0, 21.5], "pressure": [100, 101]}
    }
    assert [
        port.name
        for port in AGGREGATE_LISTS_TO_TABLE.ports_for_instance(graph.require_node("table"))
    ] == [
        "column_1",
        "column_2",
        "column_3",
        "table",
    ]


def test_aggregate_lists_to_table_rejects_unequal_lengths() -> None:
    source = NodeDefinition(
        id="unequal-vectors",
        icon="",
        label="Unequal vectors",
        ports=(
            PortDefinition("left", PortDirection.OUTPUT, LIST_INT),
            PortDefinition("right", PortDirection.OUTPUT, LIST_INT),
        ),
        executor=lambda _inputs, _parameters: {"left": [1], "right": [2, 3]},
    )
    registry = _registry(source, AGGREGATE_LISTS_TO_TABLE)
    graph = WorkflowGraph(
        [NodeInstance("source", source.id), NodeInstance("table", AGGREGATE_LISTS_TO_TABLE.id)]
    )
    graph.add_edge(WorkflowEdge("source", "left", "table", "column_1"), registry)
    graph.add_edge(WorkflowEdge("source", "right", "table", "column_2"), registry)

    with pytest.raises(Exception, match="same length"):
        WorkflowExecutor(registry).run(graph)


def _mesh_document() -> MeshDocument:
    mesh = Mesh()
    mesh.SetNodes([[0, 0, 0], [1, 0, 0], [0, 1, 0]], generateOriginalIDs=True)
    elements = mesh.GetElementsOfType(ED.Triangle_3)
    elements.AddNewElement([0, 1, 2], originalId=0)
    document = MeshDocument(mesh)
    mesh.nodeFields["temperature"] = np.array([20.0, 21.5, 22.0])
    mesh.nodeFields["velocity"] = np.array([[1, 0], [0, 1], [1, 1]])
    mesh.elemFields["pressure"] = np.array([101.0])
    return document


def test_mesh_to_table_is_registered_with_internal_selector() -> None:
    assert ADAPTERS.require("mesh-to-table") is MESH_TO_TABLE
    assert [(port.name, port.data_type) for port in MESH_TO_TABLE.inputs] == [
        ("mesh", MESH_DOCUMENT)
    ]
    assert [(port.name, port.data_type) for port in MESH_TO_TABLE.outputs] == [
        ("table", TABLE_DOCUMENT)
    ]
    assert MESH_TO_TABLE.input("entity") is None
    selector = MESH_TO_TABLE.parameters[0]
    assert selector.name == "entity"
    assert selector.port is False
    assert selector.default == "node"
    assert [(option.value, option.label) for option in selector.options] == [
        ("node", "Node data"),
        ("cell", "Cell data"),
    ]


@pytest.mark.parametrize(
    ("entity", "expected"),
    [
        (
            "node",
            {
                "flowgraph_node_id": [0, 1, 2],
                "temperature": [20.0, 21.5, 22.0],
                "velocity": [[1, 0], [0, 1], [1, 1]],
            },
        ),
        ("cell", {"flowgraph_element_id": [0], "pressure": [101.0]}),
    ],
)
def test_mesh_to_table_executes_in_workflow(entity, expected) -> None:
    document = _mesh_document()
    source = NodeDefinition(
        id="mesh-source",
        icon="",
        label="Mesh source",
        ports=(PortDefinition("mesh", PortDirection.OUTPUT, MESH_DOCUMENT),),
        executor=lambda _inputs, _parameters: {"mesh": document},
    )
    registry = _registry(source, MESH_TO_TABLE)
    graph = WorkflowGraph(
        [
            NodeInstance("source", source.id),
            MESH_TO_TABLE.create_instance("convert", parameters={"entity": entity}),
        ]
    )
    graph.add_edge(WorkflowEdge("source", "mesh", "convert", "mesh"), registry)

    result = WorkflowExecutor(registry).run(graph)

    assert result.node_outputs["convert"]["table"] == expected
    assert list(document.mesh.nodeFields) == ["flowgraph_node_id", "temperature", "velocity"]
    assert list(document.mesh.elemFields) == ["flowgraph_element_id", "pressure"]
    assert isinstance(result.node_outputs["convert"]["table"][next(iter(expected))], list)


def test_mesh_to_table_defaults_to_node_fields() -> None:
    table = MESH_TO_TABLE.executor({"mesh": _mesh_document()}, {})["table"]
    assert list(table) == ["flowgraph_node_id", "temperature", "velocity"]


def test_mesh_to_table_rejects_invalid_entity_and_field_length() -> None:
    document = _mesh_document()
    with pytest.raises(ValueError, match="entity must be 'node' or 'cell'"):
        MESH_TO_TABLE.executor({"mesh": document}, {"entity": "face"})

    document.mesh.elemFields["pressure"] = np.array([1.0, 2.0])
    with pytest.raises(ValueError, match="cell field 'pressure' must have 1 rows"):
        MESH_TO_TABLE.executor({"mesh": document}, {"entity": "cell"})
