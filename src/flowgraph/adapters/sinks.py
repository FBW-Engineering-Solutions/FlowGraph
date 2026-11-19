from collections.abc import Mapping
from typing import Any

from flowgraph.adapters.data_types import (
    ANY,
    BOOLEAN,
    IMAGE,
    MESH_DOCUMENT,
    STRING,
    TABLE_DOCUMENT,
    VEC2D,
    VEC2DI,
)
from flowgraph.application.workflow_core import (
    ExecContext,
    NodeDefinition,
    ParameterDefinition,
    ParameterOption,
    PortDefinition,
    PortDirection,
)


def _consume_mesh(
    _inputs: Mapping[str, Any],
    _parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Terminate a mesh branch; the application renders this resolved input."""
    return {}


TO_3D_VIEW = NodeDefinition(
    id="mesh-sink",
    requirements=(),
    icon="mdi-cube-scan",
    label="To 3D View",
    description="Displays an input mesh document in the 3D view.",
    ports=(PortDefinition("mesh", PortDirection.INPUT, MESH_DOCUMENT, "Mesh"),),
    executor=_consume_mesh,
    parameters=(
        ParameterDefinition(
            "color_field",
            STRING,
            "Color field",
            "",
            "Scalar field name (empty for solid color)",
            options=(ParameterOption("", "Solid color"),),
            port=False,
        ),
        ParameterDefinition(
            "show_representation",
            BOOLEAN,
            "Show representation",
            True,
            port=False,
        ),
        ParameterDefinition(
            "show_axis_grid",
            BOOLEAN,
            "Show axis grid",
            False,
            port=False,
        ),
    ),
)


SHOW_IMAGE = NodeDefinition(
    id="local-view",
    requirements=(),
    icon="mdi-image-outline",
    label="Show Image",
    description="Displays an image in a viewport within this node.",
    ports=(PortDefinition("input", PortDirection.INPUT, IMAGE, "Image"),),
    executor=_consume_mesh,
    presentation="local-view",
)


def _region_of_interest(
    _inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Return immutable image coordinates without copying the optional image."""
    corners = []
    for name in ("corner1", "corner2"):
        value = parameters[name]
        if len(value) != 2 or any(type(component) is not int for component in value):
            raise ValueError(f"{name} must contain exactly two integers")
        corners.append(tuple(value))
    return {
        "roi": tuple(corners),
        "point1": [float(component) for component in corners[0]],
        "point2": [float(component) for component in corners[1]],
    }


REGION_OF_INTEREST = NodeDefinition(
    id="image-roi",
    requirements=(),
    icon="mdi-image-outline",
    label="ROI",
    description="Defines a rectangular image region using two integer pixel coordinates.",
    ports=(
        PortDefinition("input", PortDirection.INPUT, IMAGE, "Image", required=False),
        PortDefinition("roi", PortDirection.OUTPUT, ANY, "ROI"),
        PortDefinition("point1", PortDirection.OUTPUT, VEC2D, "Point 1"),
        PortDefinition("point2", PortDirection.OUTPUT, VEC2D, "Point 2"),
    ),
    executor=_region_of_interest,
    parameters=(
        ParameterDefinition("corner1", VEC2DI, "Corner 1", [0, 0], port=False),
        ParameterDefinition("corner2", VEC2DI, "Corner 2", [0, 0], port=False),
    ),
    presentation="image-roi",
)


def _line_of_interest(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Return immutable endpoints in their original order, without copying the image."""
    outputs = dict(_region_of_interest(inputs, parameters, exec_context))
    outputs["loi"] = outputs.pop("roi")
    return outputs


LINE_OF_INTEREST = NodeDefinition(
    id="image-loi",
    requirements=(),
    icon="mdi-image-outline",
    label="LOI",
    description="Defines a line of interest using two integer pixel coordinates.",
    ports=(
        PortDefinition("input", PortDirection.INPUT, IMAGE, "Image", required=False),
        PortDefinition("loi", PortDirection.OUTPUT, ANY, "LOI"),
        PortDefinition("point1", PortDirection.OUTPUT, VEC2D, "Point 1"),
        PortDefinition("point2", PortDirection.OUTPUT, VEC2D, "Point 2"),
    ),
    executor=_line_of_interest,
    parameters=(
        ParameterDefinition("corner1", VEC2DI, "Point 1", [0, 0], port=False),
        ParameterDefinition("corner2", VEC2DI, "Point 2", [0, 0], port=False),
    ),
    presentation="image-loi",
)


def _consume_value(
    _inputs: Mapping[str, Any],
    _parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Terminate a value branch; the application renders the resolved input."""
    return {}


DISPLAY_VALUE = NodeDefinition(
    id="show-value",
    requirements=(),
    icon="mdi-text-box-outline",
    label="Show Value",
    description="Displays the string representation of any input value on the workflow.",
    ports=(PortDefinition("value", PortDirection.INPUT, ANY, "Value"),),
    executor=_consume_value,
    presentation="value",
)

PLOT_TABLE = NodeDefinition(
    id="plot-table",
    requirements=(),
    icon="mdi-chart-line",
    label="Plot Table",
    description="Plots numeric table columns in the workflow view.",
    ports=(PortDefinition("table", PortDirection.INPUT, TABLE_DOCUMENT, "Table"),),
    executor=_consume_value,
    presentation="plot-table",
)


AVAILABLE_NODES = (
    TO_3D_VIEW,
    SHOW_IMAGE,
    REGION_OF_INTEREST,
    LINE_OF_INTEREST,
    DISPLAY_VALUE,
    PLOT_TABLE,
)
