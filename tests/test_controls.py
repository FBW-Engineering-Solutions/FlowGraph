"""Typed slider parameter ports and execution behavior."""

import pytest

from flowgraph.adapters.controls import FLOAT_SLIDER, INT_SLIDER
from flowgraph.adapters.data_types import FLOAT, INTEGER
from flowgraph.adapters.simple_sources import SET_FLOAT, SET_INT
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import (
    NodeExecutionError,
    WorkflowEdge,
    WorkflowExecutor,
    WorkflowGraph,
)
from flowgraph.application.workflow_io import load_workflow, save_workflow


@pytest.mark.parametrize("slider, data_type", [(FLOAT_SLIDER, FLOAT), (INT_SLIDER, INTEGER)])
def test_slider_parameters_are_optional_typed_input_ports(slider, data_type) -> None:
    assert [(port.name, port.data_type) for port in slider.inputs] == [
        ("min", data_type),
        ("max", data_type),
        ("value", data_type),
    ]
    assert all(port.is_param and not port.required for port in slider.inputs)
    assert [(port.name, port.data_type) for port in slider.outputs] == [("value", data_type)]


@pytest.mark.parametrize("slider, expected", [(FLOAT_SLIDER, 0.5), (INT_SLIDER, 50)])
def test_slider_without_connection_uses_configured_value(slider, expected) -> None:
    graph = WorkflowGraph([slider.create_instance("slider")])
    result = WorkflowExecutor(create_node_registry()).run(graph)
    assert result.node_inputs["slider"] == {}
    assert result.node_outputs["slider"] == {"value": expected}
    assert type(result.node_outputs["slider"]["value"]) is type(expected)


@pytest.mark.parametrize(
    "slider, source, value", [(FLOAT_SLIDER, SET_FLOAT, 0.75), (INT_SLIDER, SET_INT, 75)]
)
def test_connected_slider_value_overrides_local_value_and_round_trips(
    tmp_path, slider, source, value
) -> None:
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            source.create_instance("source", parameters={"value": value}),
            slider.create_instance("slider"),
        ]
    )
    graph.add_edge(WorkflowEdge("source", "value", "slider", "value"), registry)
    path = tmp_path / "slider.json"
    save_workflow(graph, path)
    restored = load_workflow(path, registry)

    result = WorkflowExecutor(registry).run(restored)

    assert result.node_inputs["slider"] == {"value": value}
    assert result.node_outputs["slider"] == {"value": value}
    assert type(result.node_outputs["slider"]["value"]) is type(value)
    assert restored.require_node("slider").parameters["value"] == value


@pytest.mark.parametrize(
    "slider, source, value", [(FLOAT_SLIDER, SET_FLOAT, 2.0), (INT_SLIDER, SET_INT, 101)]
)
def test_connected_slider_value_still_requires_valid_range(slider, source, value) -> None:
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            source.create_instance("source", parameters={"value": value}),
            slider.create_instance("slider"),
        ]
    )
    graph.add_edge(WorkflowEdge("source", "value", "slider", "value"), registry)
    with pytest.raises(NodeExecutionError, match="between its minimum and maximum"):
        WorkflowExecutor(registry).run(graph)
