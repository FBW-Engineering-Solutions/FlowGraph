"""Tests for configurable scalar source nodes."""

import pytest

from flowgraph.adapters.simple_sources import SET_BOOLEAN
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import WorkflowExecutor, WorkflowGraph


@pytest.mark.parametrize("value", [False, True])
def test_boolean_input_outputs_configured_value(value: bool) -> None:
    registry = create_node_registry()
    assert registry.require("set-boolean") is SET_BOOLEAN
    graph = WorkflowGraph([SET_BOOLEAN.create_instance("source", parameters={"value": value})])

    result = WorkflowExecutor(registry).run(graph)

    assert result.node_outputs["source"]["value"] is value
    assert SET_BOOLEAN.output("value").data_type.id == "boolean"
    assert SET_BOOLEAN.input("value").data_type.id == "boolean"


def test_boolean_input_defaults_to_false() -> None:
    instance = SET_BOOLEAN.create_instance("source")
    assert instance.parameters["value"] is False
    result = WorkflowExecutor(create_node_registry()).run(WorkflowGraph([instance]))
    assert result.node_outputs["source"]["value"] is False


@pytest.mark.parametrize("invalid", [0, 1, "true", None])
def test_boolean_input_rejects_non_boolean_values(invalid: object) -> None:
    with pytest.raises(TypeError, match="configured boolean value must be a boolean"):
        SET_BOOLEAN.executor({}, {"value": invalid})
