import pytest

from flowgraph.adapters.data_types import LIST_FLOAT, LIST_INT
from flowgraph.adapters.table_tools import AGGREGATE_LISTS_TO_TABLE
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
