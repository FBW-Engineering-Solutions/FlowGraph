from collections.abc import Mapping
from typing import Any

from flowgraph.adapters.data_types import ANY, BOOLEAN, IMAGE, MESH_DOCUMENT, STRING
from flowgraph.application.workflow_core import (
    NodeDefinition,
    ParameterDefinition,
    ParameterOption,
    PortDefinition,
    PortDirection,
)


def _consume_mesh(_inputs: Mapping[str, Any], _parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Terminate a mesh branch; the application renders this resolved input."""
    return {}


TO_3D_VIEW = NodeDefinition(
    id="mesh-sink",
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
    icon="mdi-image-outline",
    label="Show Image",
    description="Displays an image in a viewport within this node.",
    ports=(PortDefinition("input", PortDirection.INPUT, IMAGE, "Image"),),
    executor=_consume_mesh,
    presentation="local-view",
)


def _consume_value(_inputs: Mapping[str, Any], _parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Terminate a value branch; the application renders the resolved input."""
    return {}


DISPLAY_VALUE = NodeDefinition(
    id="show-value",
    icon="mdi-text-box-outline",
    label="Show Value",
    description="Displays the string representation of any input value on the workflow.",
    ports=(PortDefinition("value", PortDirection.INPUT, ANY, "Value"),),
    executor=_consume_value,
    presentation="value",
)

AVAILABLE_NODES = (TO_3D_VIEW, SHOW_IMAGE, DISPLAY_VALUE)
