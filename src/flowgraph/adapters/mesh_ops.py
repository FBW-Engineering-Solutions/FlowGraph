"""Workflow nodes for mesh transformations and tag operations."""

from collections.abc import Mapping
from typing import Any

import numpy as np
from Muscat.LinAlg.Transform import Transform
from Muscat.MeshContainers import ElementsDescription as ED
from Muscat.MeshContainers.ElementsContainers import AllElements, ElementsContainer
from Muscat.MeshContainers.Filters.FilterObjects import ElementFilter
from Muscat.MeshContainers.Filters.FilterOperators import FilterOperatorBase
from Muscat.MeshTools.MeshCreationTools import QuadToLin
from Muscat.Types import MuscatIndex
from scipy.spatial import Delaunay

from flowgraph.adapters.data_types import MESH_DOCUMENT, MUSCAT_ELEMENT_FILTER, TRANSFORM_T
from flowgraph.application.workflow_core import (
    NodeDefinition,
    ParameterDefinition,
    ParameterOption,
    PortDefinition,
    PortDirection,
)
from flowgraph.domain.mesh_document import MeshDocument

from .data_types import ParameterKind


def _transform_mesh(_inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Build a :class:`Muscat.LinAlg.Transform.Transform` from node parameters."""
    res = Transform()
    res.keepNormalized = parameters.get("keepNormalized", True)
    res.keepOrthogonal = parameters.get("keepOrthogonal", True)
    res.SetOffset(parameters.get("translation", [0, 0, 0]))
    res.SetFirst(parameters.get("first", [1, 0, 0]))
    res.SetSecond(parameters.get("second", [0, 1, 0]))

    return {"Transform": res}


def _apply_transform(inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Apply a Muscat transform to a mesh document without mutating its input."""
    document: MeshDocument = inputs["mesh"]
    transform: Transform = inputs["Transform"]
    inverse = parameters.get("inverse", False)

    transformed_document = MeshDocument(document.mesh.View())
    apply_transform = transform.ApplyInvTransform if inverse else transform.ApplyTransform
    apply_transform_direction = (
        transform.ApplyInvTransformDirection if inverse else transform.ApplyTransformDirection
    )
    transformed_document.mesh.nodes = np.ascontiguousarray(
        apply_transform(transformed_document.mesh.nodes)
    )

    if parameters.get("onVectorFields", True):
        for fields in (
            transformed_document.mesh.nodeFields,
            transformed_document.mesh.elemFields,
        ):
            for name, field in fields.items():
                if np.ndim(field) == 2 and np.shape(field)[1] == 3:
                    fields[name] = np.ascontiguousarray(apply_transform_direction(field))

    return {"mesh": transformed_document}


def _delaunay_3d(inputs: Mapping[str, Any], _parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Tetrahedralize a document's points while preserving node metadata."""
    source = inputs["meshDocument"]
    points = np.asarray(source.mesh.nodes)
    triangulation = Delaunay(points)

    mesh = source.mesh.View()
    mesh.elements = AllElements()
    mesh.elemFields = {}
    elements = ElementsContainer(ED.ElementType.Tetrahedron_4)
    elements.AddNewElements(np.asarray(triangulation.simplices, dtype=MuscatIndex))
    mesh.elements.AddContainer(elements)
    return {"meshDocument": MeshDocument(mesh)}


def _quad_to_lin(inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Convert a quadratic mesh document to a linear mesh document."""
    input_document: MeshDocument = inputs["inputMesh"]
    mesh = QuadToLin(
        input_document.mesh,
        divideQuadElements=parameters.get("divideQuadElements", True),
        linearizedMiddlePoints=parameters.get("linearizedMiddlePoints", False),
    )
    return {"outputMesh": MeshDocument(mesh)}


_TAG_ENTITIES = ("element", "node")
_TAG_ENTITY_OPTIONS = tuple(ParameterOption(entity, entity.title()) for entity in _TAG_ENTITIES)


def _tag_collections(document: MeshDocument, entity: str):
    """Return the Muscat tag collections for a node or element tag domain."""
    if entity not in _TAG_ENTITIES:
        raise ValueError(f"tag entity must be one of {_TAG_ENTITIES!r}, got {entity!r}")
    if entity == "node":
        return (document.mesh.nodesTags,)
    return tuple(elements.tags for elements in document.mesh.elements.values())


def _validate_tag_name(name: Any, parameter: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{parameter} must be a non-empty string")
    return name.strip()


def _require_tag(collections, name: str) -> None:
    if not any(name in collection for collection in collections):
        raise ValueError(f"Tag {name!r} does not exist")


def _copy_document(document: MeshDocument) -> MeshDocument:
    return MeshDocument(document.mesh.View())


def _rename_tag(inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Rename a node or element tag without mutating the input document."""
    document = _copy_document(inputs["mesh"])
    collections = _tag_collections(document, parameters.get("entity", "element"))
    name = _validate_tag_name(parameters.get("tag"), "tag")
    new_name = _validate_tag_name(parameters.get("newTag"), "newTag")
    _require_tag(collections, name)
    if name != new_name and any(new_name in collection for collection in collections):
        raise ValueError(f"Tag {new_name!r} already exists")
    for collection in collections:
        if name in collection:
            collection.RenameTag(name, new_name)
    return {"mesh": document}


def _merge_tags(inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Merge source node or element tags into a destination tag."""
    document = _copy_document(inputs["mesh"])
    collections = _tag_collections(document, parameters.get("entity", "element"))
    target = _validate_tag_name(parameters.get("targetTag"), "targetTag")
    sources = parameters.get("sourceTags")
    if not isinstance(sources, list) or not sources:
        raise ValueError("sourceTags must be a non-empty list of strings")
    source_names = [_validate_tag_name(source, "sourceTags item") for source in sources]
    if len(set(source_names)) != len(source_names):
        raise ValueError("sourceTags must not contain duplicates")
    if target in source_names:
        raise ValueError("targetTag must not be one of sourceTags")
    for source in source_names:
        _require_tag(collections, source)
    for collection in collections:
        matching = [collection[source] for source in source_names if source in collection]
        if matching:
            destination = collection.CreateTag(target, False)
            for source in matching:
                destination.Merge(source)
            collection.DeleteTags(source_names)
    return {"mesh": document}


def _remove_tag(inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Remove a node or element tag without mutating the input document."""
    document = _copy_document(inputs["mesh"])
    collections = _tag_collections(document, parameters.get("entity", "element"))
    name = _validate_tag_name(parameters.get("tag"), "tag")
    _require_tag(collections, name)
    for collection in collections:
        collection.DeleteTags(name)
    return {"mesh": document}


def _create_tag(inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Create a tag containing the entities selected by an element filter."""
    document = _copy_document(inputs["mesh"])
    name = _validate_tag_name(parameters.get("tagName"), "tagName")
    element_filter: ElementFilter | FilterOperatorBase = inputs["filter"]
    overwrite = parameters.get("overwrite", False)

    if parameters.get("nodeTag", False):
        if name in document.mesh.nodesTags and not overwrite:
            raise ValueError(f"Tag {name!r} already exists")
        document.mesh.nodesTags.CreateTag(name).SetIds(
            element_filter.GetNodesIndices(document.mesh)
        )
    else:
        element_types = tuple(document.mesh.elements.keys())
        if (
            any(name in document.mesh.elements[element_type].tags for element_type in element_types)
            and not overwrite
        ):
            raise ValueError(f"Tag {name!r} already exists")
        for element_type in element_types:
            ids = element_filter.GetIdsToTreat(document.mesh, element_type)
            document.mesh.elements[element_type].tags.CreateTag(name).SetIds(ids)

    return {"mesh": document}


def _tag_parameters(*, merge: bool = False, rename: bool = False):
    parameters = [
        ParameterDefinition(
            "entity",
            ParameterKind.STR_SELECT,
            "Tag entity",
            "element",
            options=_TAG_ENTITY_OPTIONS,
            port=False,
        ),
    ]
    if merge:
        parameters.extend(
            [
                ParameterDefinition("sourceTags", ParameterKind.LIST_STR, "Source tags", []),
                ParameterDefinition("targetTag", ParameterKind.TEXT, "Target tag", "merged"),
            ]
        )
    else:
        parameters.append(ParameterDefinition("tag", ParameterKind.TEXT, "Tag", ""))
        if rename:
            parameters.append(ParameterDefinition("newTag", ParameterKind.TEXT, "New tag", ""))
    return tuple(parameters)


def _tag_node(node_id: str, label: str, executor, parameters) -> NodeDefinition:
    icons = {
        "Rename Tag": "mdi-tag-edit-outline",
        "Merge Tags": "mdi-tag-multiple-outline",
        "Remove Tag": "mdi-tag-remove-outline",
    }
    return NodeDefinition(
        id=node_id,
        icon=icons[label],
        label=label,
        description=f"{label} for node or element tags.",
        ports=(
            PortDefinition("mesh", PortDirection.INPUT, MESH_DOCUMENT, "Mesh"),
            PortDefinition("mesh", PortDirection.OUTPUT, MESH_DOCUMENT, "Mesh"),
        ),
        parameters=parameters,
        executor=executor,
    )


RENAME_TAG_NODE = _tag_node("rename-tag", "Rename Tag", _rename_tag, _tag_parameters(rename=True))
MERGE_TAGS_NODE = _tag_node("merge-tags", "Merge Tags", _merge_tags, _tag_parameters(merge=True))
REMOVE_TAG_NODE = _tag_node("remove-tag", "Remove Tag", _remove_tag, _tag_parameters())

CREATE_TAG_NODE = NodeDefinition(
    id="create-tag",
    icon="mdi-tag-plus-outline",
    label="Create Tag",
    description="Creates a node or element tag from an element filter.",
    ports=(
        PortDefinition("mesh", PortDirection.INPUT, MESH_DOCUMENT, "Mesh"),
        PortDefinition("filter", PortDirection.INPUT, MUSCAT_ELEMENT_FILTER, "Element Filter"),
        PortDefinition("mesh", PortDirection.OUTPUT, MESH_DOCUMENT, "Mesh"),
    ),
    parameters=(
        ParameterDefinition("tagName", ParameterKind.TEXT, "Tag name", ""),
        ParameterDefinition(
            "nodeTag", ParameterKind.BOOLEAN, "Node tag (Element tag if False)", False, port=False
        ),
        ParameterDefinition(
            "overwrite", ParameterKind.BOOLEAN, "Overwrite tag if exists", False, port=False
        ),
    ),
    executor=_create_tag,
)


TRANSFORM_NODE = NodeDefinition(
    id="transform",
    icon="mdi-axis-arrow-lock",
    label="Mesh Transform",
    description="Creates a Muscat coordinate transformation.",
    ports=(PortDefinition("Transform", PortDirection.OUTPUT, TRANSFORM_T, "Transform"),),
    executor=_transform_mesh,
    parameters=(
        ParameterDefinition("translation", ParameterKind.VEC3D, "Translation", [0, 0, 0]),
        ParameterDefinition("first", ParameterKind.VEC3D, "First direction", [1, 0, 0]),
        ParameterDefinition("second", ParameterKind.VEC3D, "Second direction", [0, 1, 0]),
        ParameterDefinition(
            "keepNormalized", ParameterKind.BOOLEAN, "Keep normalized", True, port=False
        ),
        ParameterDefinition(
            "keepOrthogonal", ParameterKind.BOOLEAN, "Keep orthogonal", True, port=False
        ),
    ),
)

APPLY_TRANSFORM_NODE = NodeDefinition(
    id="apply-transform",
    icon="mdi-vector-combine",
    label="Apply Transform",
    description="Applies a coordinate transformation to a mesh.",
    ports=(
        PortDefinition("mesh", PortDirection.INPUT, MESH_DOCUMENT, "Mesh"),
        PortDefinition("Transform", PortDirection.INPUT, TRANSFORM_T, "Transform"),
        PortDefinition("mesh", PortDirection.OUTPUT, MESH_DOCUMENT, "Transformed mesh"),
    ),
    parameters=(
        ParameterDefinition(
            "onVectorFields", ParameterKind.BOOLEAN, "Apply on Vector Fields", True, port=False
        ),
        ParameterDefinition(
            "inverse", ParameterKind.BOOLEAN, "Apply inverse transform", False, port=False
        ),
    ),
    executor=_apply_transform,
)

DELAUNAY_3D_NODE = NodeDefinition(
    id="delaunay-3d",
    icon="mdi-vector-triangle",
    label="Delaunay 3D",
    description="Create a 3D tetrahedralization from the mesh document's points.",
    ports=(
        PortDefinition("meshDocument", PortDirection.INPUT, MESH_DOCUMENT, "Mesh document"),
        PortDefinition("meshDocument", PortDirection.OUTPUT, MESH_DOCUMENT, "Mesh document"),
    ),
    executor=_delaunay_3d,
)

QUAD_TO_LIN_NODE = NodeDefinition(
    id="quad-to-lin",
    icon="mdi-vector-square-remove",
    label="Quad To Lin",
    description="Convert quadratic mesh elements to linear elements.",
    ports=(
        PortDefinition("inputMesh", PortDirection.INPUT, MESH_DOCUMENT, "Input mesh"),
        PortDefinition("outputMesh", PortDirection.OUTPUT, MESH_DOCUMENT, "Output mesh"),
    ),
    parameters=(
        ParameterDefinition(
            "divideQuadElements",
            ParameterKind.BOOLEAN,
            "Divide quadratic elements",
            True,
            port=False,
        ),
        ParameterDefinition(
            "linearizedMiddlePoints",
            ParameterKind.BOOLEAN,
            "Linearize middle points",
            False,
            port=False,
        ),
    ),
    executor=_quad_to_lin,
)

AVAILABLE_NODES = (
    TRANSFORM_NODE,
    APPLY_TRANSFORM_NODE,
    DELAUNAY_3D_NODE,
    QUAD_TO_LIN_NODE,
    RENAME_TAG_NODE,
    MERGE_TAGS_NODE,
    REMOVE_TAG_NODE,
    CREATE_TAG_NODE,
)
