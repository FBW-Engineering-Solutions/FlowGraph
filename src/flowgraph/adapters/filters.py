"""Workflow nodes that transform canonical meshes with Muscat operations."""

from collections.abc import Mapping, Sequence
from typing import Any

import Muscat.MeshContainers.ElementsDescription as ED
from Muscat.MeshContainers.Filters.FilterObjects import ElementFilter
from Muscat.MeshContainers.Filters.FilterOperators import FilterOperatorBase
from Muscat.MeshTools.MeshInspectionTools import ExtractElementsByElementFilter

from flowgraph.adapters.readers import MESH_DOCUMENT
from flowgraph.application.workflow_core import (
    NodeDefinition,
    ParameterDefinition,
    ParameterOption,
    PortDefinition,
    PortDirection,
)
from flowgraph.domain.mesh_document import MeshDocument

from .data_types import MUSCAT_ELEMENT_FILTER, ParameterKind

ELEMENT_DIMENSION_OPTIONS = (0, 1, 2, 3)
ELEMENT_TYPE_OPTIONS = tuple(
    element_type.name
    for element_type in ED.ElementType
    if element_type is not ED.ElementType.Element_NA
)


def _parameter_list(parameters: Mapping[str, Any], name: str) -> Sequence[Any]:
    """Return one list-like node parameter with a clear validation error."""
    values = parameters.get(name, ())
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"Element filter parameter {name!r} must be a list")
    return values


def _tag_list(parameters: Mapping[str, Any], name: str) -> list[str]:
    """Return a validated list of tag names for a Muscat element filter."""
    values = _parameter_list(parameters, name)
    tags: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise TypeError(f"Element filter parameter {name!r} must contain strings")
        tags.append(value)
    return tags


def _create_element_filter(
    _inputs: Mapping[str, Any], parameters: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Create a Muscat element filter from JSON-serializable selections."""
    raw_dimensions = _parameter_list(parameters, "dimensionality")
    dimensionality: list[int] = []
    for value in raw_dimensions:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("Element filter dimensions must be integers")
        if value not in ELEMENT_DIMENSION_OPTIONS:
            raise ValueError(f"Unsupported element dimension: {value}")
        if value not in dimensionality:
            dimensionality.append(value)

    raw_element_types = _parameter_list(parameters, "element_types")
    element_types: list[ED.ElementType] = []
    for name in raw_element_types:
        if not isinstance(name, str):
            raise TypeError("Element filter element types must be names")
        if name not in ELEMENT_TYPE_OPTIONS:
            raise ValueError(f"Unknown Muscat element type: {name!r}")
        element_type = ED.ElementType[name]
        if element_type not in element_types:
            element_types.append(element_type)

    node_tags = _tag_list(parameters, "ntag")
    element_tags = _tag_list(parameters, "etag")

    return {
        "filter": ElementFilter(
            dimensionality=dimensionality or None,
            elementType=element_types or None,
            nTag=node_tags or None,
            eTag=element_tags or None,
        )
    }


CREATE_MUSCAT_ELEMENT_FILTER = NodeDefinition(
    id="create-muscat-element-filter",
    icon="mdi-filter-cog-outline",
    label="Element Selector",
    description="Creates an element filter by dimensionality, element type, and tags.",
    ports=(
        PortDefinition(
            "filter",
            PortDirection.OUTPUT,
            MUSCAT_ELEMENT_FILTER,
            "Element filter",
        ),
    ),
    executor=_create_element_filter,
    parameters=(
        ParameterDefinition(
            "dimensionality",
            ParameterKind.MULTI_SELECT,
            "Dimensionality",
            [],
            options=tuple(
                ParameterOption(value, str(value)) for value in ELEMENT_DIMENSION_OPTIONS
            ),
        ),
        ParameterDefinition(
            "element_types",
            ParameterKind.MULTI_SELECT,
            "Element types",
            [],
            options=tuple(
                ParameterOption(value, value.replace("_", " ")) for value in ELEMENT_TYPE_OPTIONS
            ),
        ),
        ParameterDefinition(
            "ntag",
            ParameterKind.LIST_STR,
            "Node tags",
            [],
            placeholder="Enter node tags",
        ),
        ParameterDefinition(
            "etag",
            ParameterKind.LIST_STR,
            "Element tags",
            [],
            placeholder="Enter element tags",
        ),
    ),
)


def _filter_mesh(inputs: Mapping[str, Any], _parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Extract the elements selected by a Muscat filter into a new document."""
    document: MeshDocument = inputs["mesh"]
    element_filter: ElementFilter | FilterOperatorBase = inputs["filter"]

    filtered_mesh = ExtractElementsByElementFilter(
        document.mesh,
        element_filter,
        copy=False,
    )
    filtered_mesh.nodeFields = document.mesh.nodeFields

    filtered_document = MeshDocument(
        mesh=filtered_mesh,
    )
    return {"mesh": filtered_document}


FILTER_MESH_WITH_MUSCAT = NodeDefinition(
    id="filter-mesh-muscat",
    icon="mdi-filter-outline",
    label="Filter Mesh",
    description="Extracts mesh elements selected by a Muscat element filter.",
    ports=(
        PortDefinition("mesh", PortDirection.INPUT, MESH_DOCUMENT, "Mesh"),
        PortDefinition(
            "filter",
            PortDirection.INPUT,
            MUSCAT_ELEMENT_FILTER,
            "Element filter",
        ),
        PortDefinition("mesh", PortDirection.OUTPUT, MESH_DOCUMENT, "Filtered mesh"),
    ),
    executor=_filter_mesh,
)
