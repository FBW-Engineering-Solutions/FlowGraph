"""Simple workflow sources that produce values without reading external data."""

import ast
import math
from collections.abc import Mapping
from typing import Any

from flowgraph.application.workflow_core import (
    NodeDefinition,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
)

from .data_types import FLOAT, INTEGER, LIST_FLOAT, LIST_INT, LIST_STR, STRING, VEC3D, ParameterKind


def _set_string(_inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Output the configured string value, including an empty string."""
    value = parameters.get("value", "")
    if not isinstance(value, str):
        raise TypeError("The configured string value must be text")
    return {"value": value}


SET_STRING = NodeDefinition(
    id="set-string",
    icon="mdi-text-box-outline",
    label="String Input",
    description="Outputs a configured text value.",
    ports=(PortDefinition("value", PortDirection.OUTPUT, STRING, "Value"),),
    executor=_set_string,
    parameters=(ParameterDefinition("value", ParameterKind.TEXT, "Value", "", "Enter text"),),
)


def _set_int(_inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Output the configured integer value without accepting booleans."""
    value = parameters.get("value", 0)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("The configured integer value must be an integer")
    return {"value": value}


SET_INT = NodeDefinition(
    id="set-int",
    icon="mdi-numeric-1-box-outline",
    label="Integer Input",
    description="Outputs a configured integer value.",
    ports=(PortDefinition("value", PortDirection.OUTPUT, INTEGER, "Value"),),
    executor=_set_int,
    parameters=(ParameterDefinition("value", ParameterKind.INTEGER, "Value", 0, "0"),),
)


def _set_float(_inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Output the configured finite floating-point value."""
    value = parameters.get("value", 0.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("The configured floating-point value must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError("The configured floating-point value must be finite")
    return {"value": normalized}


SET_FLOAT = NodeDefinition(
    id="set-float",
    icon="mdi-decimal-comma",
    label="Float Input",
    description="Outputs a configured floating-point value.",
    ports=(PortDefinition("value", PortDirection.OUTPUT, FLOAT, "Value"),),
    executor=_set_float,
    parameters=(ParameterDefinition("value", ParameterKind.FLOAT, "Value", 0.0, "0.0"),),
)


def _set_vec3d(_inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Output a configured finite three-dimensional vector."""
    components = tuple(parameters.get(axis, 0.0) for axis in ("x", "y", "z"))
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in components):
        raise TypeError("The configured vector components must be numeric")

    vector = [float(value) for value in components]
    if not all(math.isfinite(value) for value in vector):
        raise ValueError("The configured vector components must be finite")
    return {"value": list(vector)}


SET_VEC3D = NodeDefinition(
    id="set-vec3d",
    icon="mdi-axis-arrow",
    label="3D Vector Input",
    description="Outputs a configured three-dimensional vector.",
    ports=(PortDefinition("value", PortDirection.OUTPUT, VEC3D, "Value"),),
    executor=_set_vec3d,
    parameters=(
        ParameterDefinition("x", ParameterKind.FLOAT, "X", 0.0, "0.0"),
        ParameterDefinition("y", ParameterKind.FLOAT, "Y", 0.0, "0.0"),
        ParameterDefinition("z", ParameterKind.FLOAT, "Z", 0.0, "0.0"),
    ),
)


def _parse_list_parameter(parameters: Mapping[str, Any]) -> list[Any]:
    """Parse a list parameter supplied by the UI or by a workflow file."""
    configured = parameters.get("value", "[]")
    try:
        value = ast.literal_eval(configured) if isinstance(configured, str) else configured
    except (SyntaxError, TypeError, ValueError):
        raise TypeError(f"Unable to convert {configured!r} to a list") from None
    if not isinstance(value, list):
        raise TypeError(f"The configured value must be a list, not {type(value).__name__}")
    return value


def _set_str_list(_inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Output a configured list of strings."""
    value = _parse_list_parameter(parameters)
    if any(not isinstance(item, str) for item in value):
        raise TypeError("The configured string list must contain only text")
    return {"value": value}


SET_LIST_STR = NodeDefinition(
    id="set-list[str]",
    icon="mdi-format-list-bulleted-square",
    label="String List Input",
    description="Outputs a configured list of str.",
    ports=(PortDefinition("value", PortDirection.OUTPUT, LIST_STR, "Value"),),
    executor=_set_str_list,
    parameters=(
        ParameterDefinition("value", ParameterKind.LIST_STR, "Value", [], "['a', 'b', 'c']"),
    ),
)


def _set_int_list(_inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Output a configured list of integers."""
    value = _parse_list_parameter(parameters)
    if any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        raise TypeError("The configured integer list must contain only integers")
    return {"value": value}


SET_LIST_INT = NodeDefinition(
    id="set-list[int]",
    icon="mdi-format-list-numbered",
    label="Integer List Input",
    description="Outputs a configured list of int.",
    ports=(PortDefinition("value", PortDirection.OUTPUT, LIST_INT, "Value"),),
    executor=_set_int_list,
    parameters=(ParameterDefinition("value", ParameterKind.LIST_INT, "Value", [], "[1, 2, 3]"),),
)


def _set_float_list(_inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Output a configured finite list of floating-point values."""
    value = _parse_list_parameter(parameters)
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
        raise TypeError("The configured float list must contain only numbers")
    normalized = [float(item) for item in value]
    if any(not math.isfinite(item) for item in normalized):
        raise ValueError("The configured float list must contain only finite numbers")
    return {"value": normalized}


SET_LIST_FLOAT = NodeDefinition(
    id="set-list[float]",
    icon="mdi-format-list-numbered-rtl",
    label="Float List Input",
    description="Outputs a configured list of float.",
    ports=(PortDefinition("value", PortDirection.OUTPUT, LIST_FLOAT, "Value"),),
    executor=_set_float_list,
    parameters=(
        ParameterDefinition("value", ParameterKind.LIST_FLOAT, "Value", [], "[1.0, 2.0, 3.0]"),
    ),
)


def _select_file(_inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Output the configured path; selecting the path itself is a UI concern."""
    path = parameters.get("path", "")
    if not isinstance(path, str):
        raise TypeError("The selected file path parameter must be text")
    if len(path) == 0:
        raise ValueError("Path can't be empty")
    return {"path": path}


AVAILABLE_NODES = (
    SET_STRING,
    SET_INT,
    SET_FLOAT,
    SET_VEC3D,
    SET_LIST_STR,
    SET_LIST_INT,
    SET_LIST_FLOAT,
)
