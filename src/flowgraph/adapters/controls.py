"""Headless workflow nodes whose values are presented with GUI controls."""

import math
from collections.abc import Mapping
from typing import Any

from flowgraph.application.workflow_core import (
    NodeDefinition,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
)

from .data_types import FLOAT, INTEGER, ParameterKind


def _slider_bounds(
    parameters: Mapping[str, Any], *, integer: bool
) -> tuple[int | float, int | float, int | float]:
    """Validate and return a slider's minimum, maximum, and current value."""
    minimum = parameters.get("min")
    maximum = parameters.get("max")
    value = parameters.get("value")
    expected_type = int if integer else (int, float)

    if (
        isinstance(minimum, bool)
        or not isinstance(minimum, expected_type)
        or isinstance(maximum, bool)
        or not isinstance(maximum, expected_type)
        or isinstance(value, bool)
        or not isinstance(value, expected_type)
    ):
        value_type = "integer" if integer else "number"
        raise TypeError(f"The slider min, max, and value must be {value_type}s")

    if integer:
        if minimum >= maximum:
            raise ValueError("The slider minimum must be less than its maximum")
    else:
        minimum = float(minimum)
        maximum = float(maximum)
        value = float(value)
        if not all(math.isfinite(item) for item in (minimum, maximum, value)):
            raise ValueError("The slider min, max, and value must be finite")
        if minimum >= maximum:
            raise ValueError("The slider minimum must be less than its maximum")

    if not minimum <= value <= maximum:
        raise ValueError("The slider value must be between its minimum and maximum")
    return minimum, maximum, value


def _float_slider(_inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Output the current finite floating-point slider value."""
    return {"value": _slider_bounds(parameters, integer=False)[2]}


FLOAT_SLIDER = NodeDefinition(
    id="float-slider",
    icon="mdi-tune-vertical",
    label="Float Slider",
    description="Outputs a floating-point value selected with a slider.",
    ports=(PortDefinition("value", PortDirection.OUTPUT, FLOAT, "Value"),),
    executor=_float_slider,
    presentation="slider",
    parameters=(
        ParameterDefinition("min", ParameterKind.FLOAT, "Minimum", 0.0, "0.0"),
        ParameterDefinition("max", ParameterKind.FLOAT, "Maximum", 1.0, "1.0"),
        ParameterDefinition("value", ParameterKind.FLOAT, "Value", 0.5, "0.5", port=False),
    ),
)


def _int_slider(_inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Output the current integer slider value."""
    return {"value": _slider_bounds(parameters, integer=True)[2]}


INT_SLIDER = NodeDefinition(
    id="int-slider",
    icon="mdi-tune-vertical",
    label="Integer Slider",
    description="Outputs an integer value selected with a slider.",
    ports=(PortDefinition("value", PortDirection.OUTPUT, INTEGER, "Value"),),
    executor=_int_slider,
    presentation="slider",
    parameters=(
        ParameterDefinition("min", ParameterKind.INTEGER, "Minimum", 0, "0"),
        ParameterDefinition("max", ParameterKind.INTEGER, "Maximum", 100, "100"),
        ParameterDefinition("value", ParameterKind.INTEGER, "Value", 50, "50", port=False),
    ),
)


AVAILABLE_NODES = (FLOAT_SLIDER, INT_SLIDER)
