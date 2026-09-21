from typing import Any

import pytest

from flowgraph.adapters.data_types import (
    FLOAT,
    INTEGER,
    LIST_FLOAT,
    LIST_INT,
    STRING,
    ParameterKind,
)
from flowgraph.application.port_conversions import resolve_port_conversion
from flowgraph.application.workflow_core import (
    DataType,
    NodeDefinition,
    NodeExecutionError,
    NodeInstance,
    NodeRegistry,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
    ValidationCode,
    WorkflowEdge,
    WorkflowExecutor,
    WorkflowGraph,
    WorkflowValidationError,
)

TEXT = DataType("text", "Text", str)
NUMBER = DataType("number", "Number", int)


def port(name: str, direction: PortDirection, data_type: DataType[Any] = TEXT) -> PortDefinition:
    return PortDefinition(name, direction, data_type)


def definition(
    definition_id: str,
    ports: tuple[PortDefinition, ...],
    executor=lambda _inputs, _parameters: {},
) -> NodeDefinition:
    return NodeDefinition(
        id=definition_id,
        icon="",
        label=definition_id.title(),
        ports=ports,
        executor=executor,
    )


def registry_with(*definitions: NodeDefinition) -> NodeRegistry:
    registry = NodeRegistry()
    for item in definitions:
        registry.register(item)
    return registry


def test_workflow_graph_rename_updates_edges_and_rejects_duplicate_ids() -> None:
    graph = WorkflowGraph(
        [NodeInstance("source", "source"), NodeInstance("sink", "sink")],
        [WorkflowEdge("source", "value", "sink", "value")],
    )

    graph.rename_node("source", "  renamed-source  ")

    assert graph.get_node("source") is None
    assert graph.get_node("renamed-source") is not None
    assert graph.edges == (WorkflowEdge("renamed-source", "value", "sink", "value"),)

    before_nodes = graph.nodes
    before_edges = graph.edges
    with pytest.raises(ValueError, match="already exists"):
        graph.rename_node("renamed-source", "sink")
    assert graph.nodes == before_nodes
    assert graph.edges == before_edges


def test_workflow_graph_rename_rejects_blank_ids_without_mutation() -> None:
    graph = WorkflowGraph([NodeInstance("source", "source")])

    with pytest.raises(ValueError, match="non-empty"):
        graph.rename_node("source", "   ")

    assert graph.get_node("source") is not None


def test_definitions_support_source_filter_sink_and_multiple_ports() -> None:
    source = definition(
        "source", (port("left", PortDirection.OUTPUT), port("right", PortDirection.OUTPUT))
    )
    transform = definition(
        "transform",
        (
            port("first", PortDirection.INPUT),
            port("second", PortDirection.INPUT),
            port("result", PortDirection.OUTPUT),
        ),
    )
    sink = definition("sink", (port("value", PortDirection.INPUT),))

    assert not source.inputs and len(source.outputs) == 2
    assert len(transform.inputs) == 2 and len(transform.outputs) == 1
    assert len(sink.inputs) == 1 and not sink.outputs


def test_definition_factory_creates_independent_configured_instances() -> None:
    source = NodeDefinition(
        id="source",
        icon="",
        label="Source",
        ports=(port("value", PortDirection.OUTPUT),),
        executor=lambda _inputs, parameters: {"value": parameters["settings"]["value"]},
        default_parameters={"settings": {"value": "default"}},
    )

    first = source.create_instance("first", x=10, y=20)
    second = source.create_instance("second", parameters={"settings": {"value": "override"}})
    first.parameters["settings"]["value"] = "changed"

    assert first.definition_id == second.definition_id == "source"
    assert (first.x, first.y) == (10, 20)
    assert second.parameters == {"settings": {"value": "override"}}
    assert source.default_parameters == {"settings": {"value": "default"}}


def test_registry_factory_delegates_to_registered_definition() -> None:
    source = definition("source", (port("value", PortDirection.OUTPUT),))
    registry = registry_with(source)

    instance = registry.create_instance("source", "configured", x=15)

    assert instance == NodeInstance("configured", "source", x=15)


def test_executor_propagates_named_values_fans_out_and_retains_outputs() -> None:
    calls: list[str] = []
    source = definition(
        "source",
        (port("value", PortDirection.OUTPUT),),
        lambda _inputs, parameters: {"value": parameters["value"]},
    )

    def uppercase(inputs, _parameters):  # type: ignore[no-untyped-def]
        calls.append("upper")
        return {"value": inputs["value"].upper()}

    transform = definition(
        "upper",
        (port("value", PortDirection.INPUT), port("value", PortDirection.OUTPUT)),
        uppercase,
    )
    seen: list[str] = []
    sink = definition(
        "sink",
        (port("value", PortDirection.INPUT),),
        lambda inputs, _parameters: seen.append(inputs["value"]) or {},
    )
    registry = registry_with(source, transform, sink)
    graph = WorkflowGraph(
        [
            NodeInstance("source", "source", {"value": "mesh"}),
            NodeInstance("upper", "upper"),
            NodeInstance("sink-a", "sink"),
            NodeInstance("sink-b", "sink"),
        ]
    )
    graph.add_edge(WorkflowEdge("source", "value", "upper", "value"), registry)
    graph.add_edge(WorkflowEdge("upper", "value", "sink-a", "value"), registry)
    graph.add_edge(WorkflowEdge("upper", "value", "sink-b", "value"), registry)

    result = WorkflowExecutor(registry).run(graph)

    assert result.execution_order == ("source", "upper", "sink-a", "sink-b")
    assert result.node_outputs["upper"] == {"value": "MESH"}
    assert result.node_inputs["sink-a"] == {"value": "MESH"}
    assert result.node_inputs["sink-b"] == {"value": "MESH"}
    assert seen == ["MESH", "MESH"]
    assert calls == ["upper"]


def test_executor_can_run_only_selected_nodes_from_cached_upstream_outputs() -> None:
    calls: list[str] = []
    source = definition(
        "source",
        (port("value", PortDirection.OUTPUT),),
        lambda _inputs, _parameters: calls.append("source") or {"value": "mesh"},
    )
    sink = definition(
        "sink",
        (port("value", PortDirection.INPUT),),
        lambda inputs, _parameters: calls.append(inputs["value"]) or {},
    )
    registry = registry_with(source, sink)
    graph = WorkflowGraph([NodeInstance("source", "source"), NodeInstance("sink", "sink")])
    graph.add_edge(WorkflowEdge("source", "value", "sink", "value"), registry)

    result = WorkflowExecutor(registry).run(
        graph,
        node_ids={"sink"},
        initial_outputs={"source": {"value": "cached"}},
    )

    assert result.execution_order == ("sink",)
    assert calls == ["cached"]


def test_connected_parameter_port_updates_the_persisted_parameter_before_execution() -> None:
    source = definition(
        "source",
        (port("value", PortDirection.OUTPUT),),
        lambda _inputs, _parameters: {"value": "from-port"},
    )
    target = NodeDefinition(
        id="target",
        icon="",
        label="Target",
        ports=(port("result", PortDirection.OUTPUT),),
        parameters=(ParameterDefinition("value", ParameterKind.TEXT, "Value", "manual"),),
        executor=lambda _inputs, parameters: {"result": parameters["value"]},
    )
    registry = registry_with(source, target)
    target_instance = target.create_instance("target")
    graph = WorkflowGraph([NodeInstance("source", "source"), target_instance])
    graph.add_edge(WorkflowEdge("source", "value", "target", "value"), registry)

    result = WorkflowExecutor(registry).run(graph)

    assert target_instance.parameters["value"] == "from-port"
    assert result.node_outputs["target"] == {"result": "from-port"}


def test_scoped_execution_reports_missing_upstream_outputs() -> None:
    source = definition("source", (port("value", PortDirection.OUTPUT),))
    sink = definition("sink", (port("value", PortDirection.INPUT),))
    registry = registry_with(source, sink)
    graph = WorkflowGraph([NodeInstance("source", "source"), NodeInstance("sink", "sink")])
    graph.add_edge(WorkflowEdge("source", "value", "sink", "value"), registry)

    with pytest.raises(NodeExecutionError, match="upstream outputs are unavailable"):
        WorkflowExecutor(registry).run(graph, node_ids={"sink"})


@pytest.mark.parametrize(
    ("edge", "expected_code"),
    [
        (WorkflowEdge("missing", "value", "sink", "value"), ValidationCode.UNKNOWN_NODE),
        (WorkflowEdge("source", "missing", "sink", "value"), ValidationCode.UNKNOWN_SOURCE_PORT),
        (WorkflowEdge("source", "value", "sink", "missing"), ValidationCode.UNKNOWN_TARGET_PORT),
    ],
)
def test_invalid_endpoints_are_rejected_transactionally(edge, expected_code) -> None:  # type: ignore[no-untyped-def]
    source = definition("source", (port("value", PortDirection.OUTPUT),))
    sink = definition("sink", (port("value", PortDirection.INPUT),))
    registry = registry_with(source, sink)
    graph = WorkflowGraph([NodeInstance("source", "source"), NodeInstance("sink", "sink")])

    with pytest.raises(WorkflowValidationError) as caught:
        graph.add_edge(edge, registry)

    assert expected_code in {issue.code for issue in caught.value.issues}
    assert graph.edges == ()


def test_type_mismatch_duplicate_input_and_cycle_are_rejected() -> None:
    text_source = definition("text-source", (port("text", PortDirection.OUTPUT),))
    number_sink = definition("number-sink", (port("number", PortDirection.INPUT, NUMBER),))
    relay = definition(
        "relay",
        (port("in", PortDirection.INPUT), port("out", PortDirection.OUTPUT)),
    )
    registry = registry_with(text_source, number_sink, relay)
    graph = WorkflowGraph(
        [
            NodeInstance("source", "text-source"),
            NodeInstance("numbers", "number-sink"),
            NodeInstance("a", "relay"),
            NodeInstance("b", "relay"),
        ]
    )
    with pytest.raises(WorkflowValidationError) as mismatch:
        graph.add_edge(WorkflowEdge("source", "text", "numbers", "number"), registry)
    assert mismatch.value.issues[0].code is ValidationCode.TYPE_MISMATCH

    graph.add_edge(WorkflowEdge("source", "text", "a", "in"), registry)
    with pytest.raises(WorkflowValidationError) as duplicate_input:
        graph.add_edge(WorkflowEdge("b", "out", "a", "in"), registry)
    assert ValidationCode.INPUT_ALREADY_CONNECTED in {
        issue.code for issue in duplicate_input.value.issues
    }

    cycle_graph = WorkflowGraph([NodeInstance("a", "relay"), NodeInstance("b", "relay")])
    cycle_graph.add_edge(WorkflowEdge("a", "out", "b", "in"), registry)
    with pytest.raises(WorkflowValidationError) as cycle:
        cycle_graph.add_edge(WorkflowEdge("b", "out", "a", "in"), registry)
    assert ValidationCode.CYCLE in {issue.code for issue in cycle.value.issues}


@pytest.mark.parametrize(
    ("source_type", "target_type", "source_value", "expected_value", "conversion_label"),
    [
        (INTEGER, FLOAT, 7, 7.0, "Integer → Float"),
        (INTEGER, STRING, 7, "7", "Integer → string"),
        (INTEGER, LIST_INT, 7, [7], "Integer → list[int]"),
        (FLOAT, INTEGER, 1.25, 1, "Float -> Integer"),
        (FLOAT, STRING, 1.25, "1.25", "Float → Text"),
        (FLOAT, LIST_FLOAT, 1.25, [1.25], "Float → list[float]"),
    ],
)
def test_registered_port_conversions_validate_and_deliver_target_values(
    source_type: DataType[Any],
    target_type: DataType[Any],
    source_value: object,
    expected_value: object,
    conversion_label: str,
) -> None:
    source = definition(
        "source",
        (port("value", PortDirection.OUTPUT, source_type),),
        lambda _inputs, _parameters: {"value": source_value},
    )
    received: list[object] = []
    sink = definition(
        "sink",
        (port("value", PortDirection.INPUT, target_type),),
        lambda inputs, _parameters: received.append(inputs["value"]) or {},
    )
    registry = registry_with(source, sink)
    edge = WorkflowEdge("source", "value", "sink", "value")
    graph = WorkflowGraph([NodeInstance("source", "source"), NodeInstance("sink", "sink")])

    graph.add_edge(edge, registry)
    result = WorkflowExecutor(registry).run(graph)

    conversion = graph.edge_conversion(edge, registry)
    assert conversion is not None
    assert conversion.label == conversion_label
    assert result.node_inputs["sink"] == {"value": expected_value}
    assert received == [expected_value]


def test_port_conversion_registry_is_explicit_and_directional() -> None:
    assert resolve_port_conversion(INTEGER, FLOAT) is not None
    assert resolve_port_conversion(FLOAT, STRING) is not None
    assert resolve_port_conversion(FLOAT, INTEGER) is not None
    assert resolve_port_conversion(STRING, STRING) is None
    assert resolve_port_conversion(STRING, FLOAT) is None


def test_execution_requires_connected_inputs_and_valid_outputs() -> None:
    bad_source = definition(
        "bad-source",
        (port("value", PortDirection.OUTPUT),),
        lambda _inputs, _parameters: {"value": 42},
    )
    sink = definition("sink", (port("value", PortDirection.INPUT),))
    registry = registry_with(bad_source, sink)
    incomplete = WorkflowGraph([NodeInstance("sink", "sink")])

    with pytest.raises(
        NodeExecutionError, match="required inputs are not connected: value"
    ) as missing:
        WorkflowExecutor(registry).run(incomplete)
    assert missing.value.node_id == "sink"
    assert missing.value.definition_id == "sink"
    assert missing.value.partial_result is not None
    assert missing.value.partial_result.execution_order == ()
    assert missing.value.partial_result.node_outputs == {}

    graph = WorkflowGraph([NodeInstance("source", "bad-source"), NodeInstance("sink", "sink")])
    graph.add_edge(WorkflowEdge("source", "value", "sink", "value"), registry)
    with pytest.raises(NodeExecutionError, match="expected Text, got int"):
        WorkflowExecutor(registry).run(graph)


@pytest.mark.parametrize(
    ("executor", "message"),
    [
        (lambda _inputs, _parameters: {"unexpected": "value"}, "expected outputs"),
        (lambda _inputs, _parameters: 42, "object is not iterable"),
        (lambda _inputs, _parameters: 1 / 0, "division by zero"),
    ],
)
def test_malformed_outputs_and_executor_failures_include_node_context(
    executor,
    message,  # type: ignore[no-untyped-def]
) -> None:
    source = definition("source", (port("value", PortDirection.OUTPUT),), executor)
    registry = registry_with(source)

    with pytest.raises(NodeExecutionError, match=message) as caught:
        WorkflowExecutor(registry).run(WorkflowGraph([NodeInstance("configured-source", "source")]))

    assert caught.value.node_id == "configured-source"
    assert caught.value.definition_id == "source"


def test_node_execution_error_preserves_only_the_validated_completed_prefix() -> None:
    source = definition(
        "source",
        (port("value", PortDirection.OUTPUT),),
        lambda _inputs, _parameters: {"value": "ready"},
    )
    failing = definition(
        "failing",
        (port("value", PortDirection.INPUT), port("result", PortDirection.OUTPUT)),
        lambda _inputs, _parameters: 1 / 0,
    )
    registry = registry_with(source, failing)
    graph = WorkflowGraph([NodeInstance("source", "source"), NodeInstance("failing", "failing")])
    graph.add_edge(WorkflowEdge("source", "value", "failing", "value"), registry)

    with pytest.raises(NodeExecutionError) as caught:
        WorkflowExecutor(registry).run(graph)

    partial = caught.value.partial_result
    assert partial is not None
    assert partial.execution_order == ("source",)
    assert partial.node_outputs == {"source": {"value": "ready"}}
    assert "failing" not in partial.node_outputs


def test_executor_continues_independent_branches_after_a_node_failure() -> None:
    failing = definition(
        "failing",
        (port("value", PortDirection.OUTPUT),),
        lambda _inputs, _parameters: 1 / 0,
    )
    independent = definition(
        "independent",
        (port("value", PortDirection.OUTPUT),),
        lambda _inputs, _parameters: {"value": "ok"},
    )
    dependent = definition(
        "dependent",
        (port("value", PortDirection.INPUT),),
        lambda _inputs, _parameters: {},
    )
    registry = registry_with(failing, independent, dependent)
    graph = WorkflowGraph(
        [
            NodeInstance("failing", "failing"),
            NodeInstance("independent", "independent"),
            NodeInstance("dependent", "dependent"),
        ]
    )
    graph.add_edge(WorkflowEdge("failing", "value", "dependent", "value"), registry)

    with pytest.raises(NodeExecutionError) as caught:
        WorkflowExecutor(registry).run(graph)

    partial = caught.value.partial_result
    assert partial is not None
    assert partial.execution_order == ("independent",)
    assert partial.node_outputs == {"independent": {"value": "ok"}}


def test_executor_runs_independent_nodes_when_another_node_has_missing_input() -> None:
    incomplete = definition("incomplete", (port("value", PortDirection.INPUT),))
    independent = definition(
        "independent",
        (port("value", PortDirection.OUTPUT),),
        lambda _inputs, _parameters: {"value": "ok"},
    )
    registry = registry_with(incomplete, independent)
    graph = WorkflowGraph(
        [NodeInstance("incomplete", "incomplete"), NodeInstance("independent", "independent")]
    )

    with pytest.raises(
        NodeExecutionError, match="required inputs are not connected: value"
    ) as caught:
        WorkflowExecutor(registry).run(graph)

    partial = caught.value.partial_result
    assert partial is not None
    assert partial.execution_order == ("independent",)
    assert partial.node_outputs == {"independent": {"value": "ok"}}


def test_workflow_exports_inputs_parameters_outputs_and_executes_like_a_node() -> None:
    transform = definition(
        "transform",
        (port("value", PortDirection.INPUT), port("result", PortDirection.OUTPUT)),
        lambda inputs, _parameters: {"result": inputs["value"].upper()},
    )
    registry = registry_with(transform)
    graph = WorkflowGraph([NodeInstance("transform", "transform")])

    graph.add_input("text", "transform", "value", registry)
    graph.add_output("result", "transform", "result", registry)

    assert graph.inputs[0].data_type is TEXT
    assert graph.outputs[0].node_port == "result"
    assert graph.execute({"text": "hello"}, registry) == {"result": "HELLO"}
    assert graph.executor(registry)({"text": "world"}) == {"result": "WORLD"}


def test_exported_parameter_input_is_free_and_supplied_to_node_parameters() -> None:
    configured = NodeDefinition(
        id="configured",
        icon="",
        label="Configured",
        ports=(PortDefinition("result", PortDirection.OUTPUT, TEXT),),
        executor=lambda _inputs, parameters: {"result": parameters["value"]},
        parameters=(ParameterDefinition("value", TEXT, "Value", "default"),),
    )
    registry = registry_with(configured)
    graph = WorkflowGraph([NodeInstance("configured", "configured", {"value": "default"})])
    graph.export_input("value", "configured", "value", registry)
    graph.export_output("result", "configured", "result", registry)

    assert graph.execute({"value": "provided"}, registry) == {"result": "provided"}


def test_exported_input_rejects_an_existing_connection() -> None:
    source = definition("source", (port("value", PortDirection.OUTPUT),))
    sink = definition("sink", (port("value", PortDirection.INPUT),))
    registry = registry_with(source, sink)
    graph = WorkflowGraph([NodeInstance("source", "source"), NodeInstance("sink", "sink")])
    graph.add_edge(WorkflowEdge("source", "value", "sink", "value"), registry)

    with pytest.raises(WorkflowValidationError, match="must not be connected"):
        graph.export_input("value", "sink", "value", registry)
