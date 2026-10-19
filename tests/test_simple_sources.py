"""Tests for configurable scalar source nodes."""

import pytest

from flowgraph.adapters.simple_sources import SET_BOOLEAN, SET_VEC2D, SET_VEC2DI
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import WorkflowEdge, WorkflowExecutor, WorkflowGraph


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


@pytest.mark.parametrize(
    ("parameters", "expected"),
    [({}, [0.0, 0.0]), ({"x": 2, "y": -1.5}, [2.0, -1.5])],
)
def test_2d_vector_input_outputs_two_float_components(
    parameters: dict[str, float], expected: list[float]
) -> None:
    registry = create_node_registry()
    assert registry.require("set-vec2d") is SET_VEC2D
    instance = SET_VEC2D.create_instance("source", parameters=parameters)
    assert SET_VEC2D.output("value").data_type.id == "VEC2D"
    assert [param.name for param in SET_VEC2D.parameters] == ["x", "y"]

    result = WorkflowExecutor(registry).run(WorkflowGraph([instance]))

    assert result.node_outputs["source"]["value"] == expected


@pytest.mark.parametrize("invalid", [True, "1", None])
@pytest.mark.parametrize("axis", ["x", "y"])
def test_2d_vector_input_rejects_non_numeric_components(axis: str, invalid: object) -> None:
    with pytest.raises(TypeError, match="vector components must be numeric"):
        SET_VEC2D.executor({}, {axis: invalid})


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("axis", ["x", "y"])
def test_2d_vector_input_rejects_non_finite_components(axis: str, invalid: float) -> None:
    with pytest.raises(ValueError, match="vector components must be finite"):
        SET_VEC2D.executor({}, {axis: invalid})


@pytest.mark.parametrize(
    ("parameters", "expected"),
    [({}, [0, 0]), ({"x": 3, "y": -2}, [3, -2])],
)
def test_2d_integer_vector_input_outputs_two_int_components(
    parameters: dict[str, int], expected: list[int]
) -> None:
    registry = create_node_registry()
    assert registry.require("set-vec2di") is SET_VEC2DI
    instance = SET_VEC2DI.create_instance("source", parameters=parameters)
    assert instance.parameters == {"x": expected[0], "y": expected[1]}
    assert SET_VEC2DI.output("value").data_type.id == "VEC2DI"
    assert [param.kind.id for param in SET_VEC2DI.parameters] == ["integer", "integer"]

    result = WorkflowExecutor(registry).run(WorkflowGraph([instance]))

    assert result.node_outputs["source"]["value"] == expected
    assert all(type(item) is int for item in result.node_outputs["source"]["value"])


@pytest.mark.parametrize("invalid", [True, 1.5, "2", None, float("nan")])
@pytest.mark.parametrize("axis", ["x", "y"])
def test_2d_integer_vector_input_rejects_non_integer_components(axis: str, invalid: object) -> None:
    with pytest.raises(TypeError, match="integer vector components must be integers"):
        SET_VEC2DI.executor({}, {axis: invalid})


def test_2d_integer_vector_input_connects_to_create_square_dimensions() -> None:
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            SET_VEC2DI.create_instance("dimensions", parameters={"x": 2, "y": 3}),
            registry.create_instance("create-square", "square"),
        ],
        [WorkflowEdge("dimensions", "value", "square", "dimensions")],
    )

    result = WorkflowExecutor(registry).run(graph)

    assert result.node_inputs["square"]["dimensions"] == [2, 3]
