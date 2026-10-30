"""Workflow nodes that transform canonical meshes with Muscat operations."""

from collections.abc import Mapping, Sequence
from typing import Any

import Muscat.MeshContainers.ElementsDescription as ED
import numpy as np
from Muscat.MeshContainers.Filters.FilterObjects import ElementFilter, NodeFilter
from Muscat.MeshContainers.Filters.FilterOperators import (
    ComplementaryFilter,
    DifferenceFilter,
    FilterOperatorBase,
    IntersectionFilter,
    UnionFilter,
)
from Muscat.MeshTools.MeshInspectionTools import ExtractElementsByElementFilter

from flowgraph.adapters.readers import MESH_DOCUMENT
from flowgraph.application.workflow_core import (
    ExecContext,
    NodeDefinition,
    ParameterDefinition,
    ParameterOption,
    PortDefinition,
    PortDirection,
)
from flowgraph.domain.mesh_document import MeshDocument

from .data_types import MUSCAT_ELEMENT_FILTER, MUSCAT_NODE_FILTER, MUSCAT_ZONE, ParameterKind

ELEMENT_DIMENSION_OPTIONS = (0, 1, 2, 3)
ELEMENT_TYPE_OPTIONS = tuple(
    element_type.name
    for element_type in ED.ElementType
    if element_type is not ED.ElementType.Element_NA
)

_NESTED_FILTER_PORTS = (
    PortDefinition(
        "nFilter", PortDirection.INPUT, MUSCAT_NODE_FILTER, "Node filter", required=False
    ),
    PortDefinition(
        "eFilter", PortDirection.INPUT, MUSCAT_ELEMENT_FILTER, "Element filter", required=False
    ),
)


def _parameter_list(parameters: Mapping[str, Any], name: str) -> Sequence[Any]:
    """Return one list-like node parameter with a clear validation error."""
    values = parameters.get(name, ())
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"Filter parameter {name!r} must be a list")
    return values


def _tag_list(parameters: Mapping[str, Any], name: str) -> list[str]:
    """Return a validated list of tag names for a Muscat selector."""
    values = _parameter_list(parameters, name)
    tags: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise TypeError(f"Filter parameter {name!r} must contain strings")
        tags.append(value)
    return tags


def _create_element_filter(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
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
            zone=[value for name, value in inputs.items() if name.startswith("zone_")],
            zonesTreatment=parameters.get("zonesTreatment", "CENTER"),
            nFilter=inputs.get("nFilter"),
            eFilter=inputs.get("eFilter"),
            nFilterTreatment=parameters.get("nFilterTreatment", "ALL_NODES"),
        )
    }


CREATE_MUSCAT_ELEMENT_FILTER = NodeDefinition(
    id="create-muscat-element-filter",
    requirements=("py:muscat",),
    icon="mdi-filter-cog-outline",
    label="Element Selector",
    description="Creates an element filter by dimensionality, element type, tags, and spatial zones.",
    ports=(
        *_NESTED_FILTER_PORTS,
        PortDefinition(
            "zone", PortDirection.INPUT, MUSCAT_ZONE, "Zone", required=False, expandable=128
        ),
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
            "nFilterTreatment",
            ParameterKind.STR_SELECT,
            "Node filter treatment",
            "ALL_NODES",
            options=(
                ParameterOption("ALL_NODES", "All nodes"),
                ParameterOption("AT_LEAST_ONE", "At least one node"),
            ),
        ),
        ParameterDefinition(
            "zonesTreatment",
            ParameterKind.STR_SELECT,
            "Zone treatment",
            "CENTER",
            options=tuple(
                ParameterOption(value, label)
                for value, label in (
                    ("CENTER", "Element center"),
                    ("ALL_NODES", "All nodes"),
                    ("AT_LEAST_ONE", "At least one node"),
                )
            ),
        ),
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


class _ComposedNodeFilter(NodeFilter):
    """Honor nested nodal filters omitted by Muscat's NodeFilter implementation."""

    def GetNodesIndices(self, mesh):
        indices = super().GetNodesIndices(mesh)
        if self.nFilter is None:
            return indices
        return np.intersect1d(indices, self.nFilter.GetNodesIndices(mesh))


def _create_node_filter(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Create a Muscat nodal selector from tags, zones, and nested selectors."""
    return {
        "filter": _ComposedNodeFilter(
            nTag=_tag_list(parameters, "ntag") or None,
            eTag=_tag_list(parameters, "etag") or None,
            zone=[value for name, value in inputs.items() if name.startswith("zone_")],
            nFilter=inputs.get("nFilter"),
            eFilter=inputs.get("eFilter"),
        )
    }


CREATE_MUSCAT_NODE_FILTER = NodeDefinition(
    id="create-muscat-node-filter",
    requirements=("py:muscat",),
    icon="mdi-filter-cog-outline",
    label="Node Selector",
    description="Creates a node filter by node/element tags, spatial zones, and nested filters.",
    ports=(
        *_NESTED_FILTER_PORTS,
        PortDefinition(
            "zone", PortDirection.INPUT, MUSCAT_ZONE, "Zone", required=False, expandable=128
        ),
        PortDefinition("filter", PortDirection.OUTPUT, MUSCAT_NODE_FILTER, "Node filter"),
    ),
    parameters=tuple(
        parameter
        for parameter in CREATE_MUSCAT_ELEMENT_FILTER.parameters
        if parameter.name in ("ntag", "etag")
    ),
    executor=_create_node_filter,
)


def _filter_mesh(
    inputs: Mapping[str, Any],
    _parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
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
    requirements=("py:muscat",),
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


def _selector_operator(operator):
    def execute(inputs, parameters, _exec_context=None):
        if operator in (UnionFilter, IntersectionFilter):
            names = sorted(
                (name for name in inputs if name.startswith("filter_")),
                key=lambda name: int(name.rsplit("_", 1)[1]),
            )
            filters = [inputs[name] for name in names]
            if not filters:
                raise ValueError("At least one selector must be connected")
        elif operator is DifferenceFilter:
            filters = [inputs["first"], inputs["second"]]
        else:
            filters = [inputs["filter"]]
        if not all(isinstance(value, (ElementFilter, FilterOperatorBase)) for value in filters):
            raise TypeError("Selector operators require element selectors")
        return {"filter": operator(filters=filters)}

    return execute


def _operator_node(name, label, operator):
    if operator in (UnionFilter, IntersectionFilter):
        inputs = (
            PortDefinition(
                "filter",
                PortDirection.INPUT,
                MUSCAT_ELEMENT_FILTER,
                "Selector",
                required=False,
                expandable=128,
            ),
        )
    else:
        names = ("first", "second") if operator is DifferenceFilter else ("filter",)
        inputs = tuple(
            PortDefinition(name, PortDirection.INPUT, MUSCAT_ELEMENT_FILTER, name.title())
            for name in names
        )
    return NodeDefinition(
        id=name,
        label=label,
        icon="mdi-filter-outline",
        requirements=("py:muscat",),
        description=f"{label} of element selections; evaluated on the consuming mesh.",
        ports=(
            *inputs,
            PortDefinition("filter", PortDirection.OUTPUT, MUSCAT_ELEMENT_FILTER, "Selector"),
        ),
        executor=_selector_operator(operator),
    )


SELECTOR_UNION = _operator_node("selector-union", "Selector Union", UnionFilter)
SELECTOR_INTERSECTION = _operator_node(
    "selector-intersection", "Selector Intersection", IntersectionFilter
)
SELECTOR_DIFFERENCE = _operator_node("selector-difference", "Selector Difference", DifferenceFilter)
SELECTOR_COMPLEMENT = _operator_node(
    "selector-complement", "Selector Complement", ComplementaryFilter
)
SELECTOR_OPERATORS = (
    SELECTOR_UNION,
    SELECTOR_INTERSECTION,
    SELECTOR_DIFFERENCE,
    SELECTOR_COMPLEMENT,
)
