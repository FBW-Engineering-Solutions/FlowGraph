"""Mesh assembly and explicit field/tag association conversions."""

from collections.abc import Mapping
from typing import Any

import numpy as np
from Muscat.MeshContainers import ElementsDescription as ED
from Muscat.MeshContainers.Filters.FilterObjects import ElementFilter, NodeFilter
from Muscat.MeshContainers.Mesh import Mesh
from Muscat.Types import MuscatIndex

from flowgraph.adapters.data_types import (
    ARRAY,
    MESH_DOCUMENT,
    MUSCAT_NODE_FILTER,
    ParameterKind,
)
from flowgraph.application.workflow_core import (
    ExecContext,
    NodeDefinition,
    ParameterDefinition,
    ParameterOption,
    PortDefinition,
    PortDirection,
)
from flowgraph.domain.mesh_document import MeshDocument

_RESERVED = {"flowgraph_node_id", "flowgraph_element_id"}


def _publish(mesh: Mesh) -> MeshDocument:
    """Validate IDs before exposing only read-only array views."""
    return MeshDocument(_view(MeshDocument(mesh).mesh))


def _view(source: Mesh) -> Mesh:
    """Preserve tags omitted by Muscat's structured element container View."""
    mesh = source.View()
    for original in source.elements:
        mesh.elements[original.elementType].tags = original.tags.View()
    return mesh


def _append_tag(collection, name, ids):
    """Store set semantics without copying unrelated tags or mesh arrays."""
    tag = collection.CreateTag(name, False)
    tag.SetIds(np.union1d(tag.GetIds(), ids))


def _name(value: Any, label: str = "Field name") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _field_name(value: Any) -> str:
    name = _name(value)
    if name in _RESERVED:
        raise ValueError("Cannot modify reserved FlowGraph ID fields")
    return name


def _fields(mesh: Mesh, entity: str) -> dict:
    if entity not in ("node", "element"):
        raise ValueError("Field association must be 'node' or 'element'")
    return mesh.nodeFields if entity == "node" else mesh.elemFields


def _dimension(parameters: Mapping[str, Any]) -> int:
    dim = parameters.get("dimensionality", -1)
    if isinstance(dim, bool) or not isinstance(dim, int) or dim not in (-1, 0, 1, 2, 3):
        raise ValueError("Dimensionality must be -1 (all), 0, 1, 2, or 3")
    return dim


def _blocks(mesh: Mesh, dimension: int):
    """Yield global slices without mutating Muscat's cached global offsets."""
    offset = 0
    for elements in mesh.elements:
        count = elements.GetNumberOfElements()
        if dimension == -1 or ED.dimensionality[elements.elementType] == dimension:
            yield elements, slice(offset, offset + count)
        offset += count


def _merge_meshes(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Assemble meshes in numeric input order without welding coincident nodes."""
    names = sorted(
        (key for key in inputs if key.startswith("mesh_")),
        key=lambda key: int(key.rsplit("_", 1)[1]),
    )
    if not names:
        raise ValueError("At least one mesh must be connected")
    sources = [inputs[name].mesh for name in names]
    if len({mesh.nodes.shape[1] for mesh in sources}) != 1:
        raise ValueError("Merged meshes must have the same coordinate dimension")
    node_counts = [mesh.GetNumberOfNodes() for mesh in sources]
    node_offsets = np.cumsum([0, *node_counts], dtype=MuscatIndex)
    result = Mesh()
    result.nodes = np.concatenate([mesh.nodes for mesh in sources])
    result.originalIDNodes = np.concatenate([mesh.originalIDNodes for mesh in sources])
    result.props = sources[0].props.copy()
    # Concatenating even two structured grids no longer describes one regular grid.
    result.props.pop("IsConstantRectilinear", None)
    for mesh, offset in zip(sources, node_offsets):
        for tag in mesh.nodesTags:
            _append_tag(result.nodesTags, tag.name, tag.GetIds() + offset)

    # Each source element maps to its position in the type-grouped merged mesh.
    mappings = [np.empty(mesh.GetNumberOfElements(), dtype=MuscatIndex) for mesh in sources]
    # Muscat AllElements iterates containers, not dictionary keys.
    types = sorted({elements.elementType for mesh in sources for elements in mesh.elements})
    global_offset = 0
    for kind in types:
        blocks = [
            (i, mesh.elements[kind]) for i, mesh in enumerate(sources) if kind in mesh.elements
        ]
        total = sum(elements.GetNumberOfElements() for _, elements in blocks)
        target = result.GetElementsOfType(kind)
        connectivity = np.empty((total, ED.numberOfNodes[kind]), dtype=MuscatIndex)
        original_ids = np.empty(total, dtype=MuscatIndex)
        local_offset = 0
        for index, elements in blocks:
            count = elements.GetNumberOfElements()
            connectivity[local_offset : local_offset + count] = (
                elements.connectivity[:count] + node_offsets[index]
            )
            original_ids[local_offset : local_offset + count] = elements.originalIds[:count]
            source_offset = sum(
                e.GetNumberOfElements() for e in sources[index].elements if e.elementType < kind
            )
            mappings[index][source_offset : source_offset + count] = (
                np.arange(count) + global_offset + local_offset
            )
            for tag in elements.tags:
                _append_tag(target.tags, tag.name, tag.GetIds() + local_offset)
            local_offset += count
        target.connectivity = connectivity
        target.originalIds = original_ids
        target.cpt = total
        global_offset += total

    for entity in ("node", "element"):
        dictionaries = [_fields(mesh, entity) for mesh in sources]
        field_names = sorted(set().union(*(fields.keys() for fields in dictionaries)) - _RESERVED)
        output_fields = _fields(result, entity)
        counts = (
            node_counts if entity == "node" else [mesh.GetNumberOfElements() for mesh in sources]
        )
        for name in field_names:
            available = [fields[name] for fields in dictionaries if name in fields]
            shapes = {data.shape[1:] for data in available}
            if len(shapes) != 1 or any(data.ndim == 0 for data in available):
                raise ValueError(f"Incompatible shapes for {entity} field {name!r}")
            dtype = np.result_type(*(data.dtype for data in available))
            # Do not silently stringify numeric values or accept object payloads.
            if dtype.hasobject or (
                dtype.kind in "US" and any(data.dtype.kind not in "US" for data in available)
            ):
                raise ValueError(f"Incompatible dtypes for {entity} field {name!r}")
            data = np.zeros((sum(counts), *available[0].shape[1:]), dtype=dtype)
            for index, (fields, count) in enumerate(zip(dictionaries, counts)):
                if name not in fields:
                    continue
                if len(fields[name]) != count:
                    raise ValueError(f"Invalid length for {entity} field {name!r}")
                ids = (
                    slice(node_offsets[index], node_offsets[index + 1])
                    if entity == "node"
                    else mappings[index]
                )
                data[ids] = fields[name]
            output_fields[name] = data
    return {"mesh": _publish(result)}


def _convert_field(to_element: bool):
    def execute(inputs, parameters, _exec_context=None):
        source = inputs["mesh"].mesh
        name = _field_name(parameters.get("fieldName", ""))
        target_name = _field_name(parameters.get("targetName", "") or name)
        origin = source.nodeFields if to_element else source.elemFields
        destination = source.elemFields if to_element else source.nodeFields
        if name not in origin:
            raise ValueError(f"Source field {name!r} does not exist")
        if target_name in destination and not parameters.get("overwrite", False):
            raise ValueError(f"Destination field {target_name!r} already exists")
        field = origin[name]
        count = source.GetNumberOfNodes() if to_element else source.GetNumberOfElements()
        if field.ndim not in (1, 2) or len(field) != count or field.dtype.kind not in "iufc":
            raise ValueError("Source field must be an entity-aligned 1D/2D numeric array")
        dim = _dimension(parameters)
        size = source.GetNumberOfElements() if to_element else source.GetNumberOfNodes()
        values = np.zeros((size, *field.shape[1:]), dtype=np.result_type(field.dtype, np.float64))
        weights = None if to_element else np.zeros(size, dtype=MuscatIndex)
        for elements, region in _blocks(source, dim):
            conn = elements.connectivity[: elements.GetNumberOfElements()]
            if to_element:
                # Bound temporary storage by processing one local node at a time.
                for local in range(conn.shape[1]):
                    values[region] += field[conn[:, local]]
                values[region] /= conn.shape[1]
            else:
                for local in range(conn.shape[1]):
                    np.add.at(values, conn[:, local], field[region])
                    np.add.at(weights, conn[:, local], 1)
        if weights is not None:
            divisor = np.maximum(weights, 1)
            values /= divisor if field.ndim == 1 else divisor[:, None]
        mesh = _view(source)
        (mesh.elemFields if to_element else mesh.nodeFields)[target_name] = values
        if parameters.get("removeSource", False):
            del (mesh.nodeFields if to_element else mesh.elemFields)[name]
        document = _publish(mesh)
        return {
            "mesh": document,
            "field": (document.mesh.elemFields if to_element else document.mesh.nodeFields)[
                target_name
            ],
        }

    return execute


def _edit_field(rename: bool):
    def execute(inputs, parameters, _exec_context=None):
        mesh = _view(inputs["mesh"].mesh)
        fields = _fields(mesh, parameters.get("entity", "node"))
        name = _field_name(parameters.get("fieldName", ""))
        if name not in fields:
            raise ValueError(f"Field {name!r} does not exist")
        if rename:
            new_name = _field_name(parameters.get("newName", ""))
            if new_name != name and new_name in fields:
                raise ValueError(f"Field {new_name!r} already exists")
            if new_name != name:
                fields[new_name] = fields.pop(name)
        else:
            del fields[name]
        return {"mesh": _publish(mesh)}

    return execute


def _tag_names(mesh: Mesh, parameters: Mapping[str, Any], from_nodes: bool) -> list[str]:
    requested = parameters.get("tags", [])
    if not isinstance(requested, (list, tuple)):
        raise TypeError("Tags must be a list of names")
    available = set(mesh.nodesTags.keys() if from_nodes else mesh.elements.GetTagsNames())
    names = (
        list(dict.fromkeys(_name(name, "Tag name") for name in requested))
        if requested
        else sorted(available)
    )
    missing = set(names) - available
    if missing:
        raise ValueError(f"Source tags do not exist: {', '.join(sorted(missing))}")
    return names


def _tag_mode(collections, name, mode):
    if mode not in ("append", "replace", "error"):
        raise ValueError("Tag mode must be append, replace, or error")
    if mode == "error" and any(name in collection for collection in collections):
        raise ValueError(f"Tag {name!r} already exists")
    if mode == "replace":
        for collection in collections:
            if name in collection:
                collection.DeleteTags(name)


def _convert_tags(to_element: bool):
    def execute(inputs, parameters, _exec_context=None):
        mesh = _view(inputs["mesh"].mesh)
        names = _tag_names(mesh, parameters, to_element)
        prefix = parameters.get("prefix", "")
        if not isinstance(prefix, str):
            raise TypeError("Tag prefix must be text")
        dim = _dimension(parameters)
        treatment = parameters.get("treatment", "all")
        if treatment not in ("all", "any"):
            raise ValueError("Node treatment must be all or any")
        for name in names:
            target = _name(prefix + name, "Target tag name")
            collections = [e.tags for e in mesh.elements] if to_element else [mesh.nodesTags]
            _tag_mode(collections, target, parameters.get("mode", "error"))
            if to_element:
                mask = np.zeros(mesh.GetNumberOfNodes(), dtype=bool)
                mask[mesh.nodesTags[name].GetIds()] = True
                for elements, _ in _blocks(mesh, dim):
                    selected = mask[elements.connectivity[: elements.GetNumberOfElements()]]
                    ids = np.flatnonzero(
                        selected.all(axis=1) if treatment == "all" else selected.any(axis=1)
                    )
                    _append_tag(elements.tags, target, ids)
            else:
                ids = []
                for elements, _ in _blocks(mesh, dim):
                    if name in elements.tags:
                        ids.append(elements.connectivity[elements.tags[name].GetIds()].ravel())
                _append_tag(mesh.nodesTags, target, np.concatenate(ids) if ids else [])
        return {"mesh": _publish(mesh)}

    return execute


def _add_tag(inputs, parameters, _exec_context=None):
    """Add a named selection as a node/element tag, optionally appending to a tag."""
    mesh = _view(inputs["mesh"].mesh)
    name = _name(parameters.get("tagName", ""), "Tag name")
    entity = parameters.get("entity", "element")
    if entity not in ("node", "element"):
        raise ValueError("Tag entity must be node or element")
    selector = inputs["filter"]
    if entity == "node":
        ids = selector.GetNodesIndices(mesh)
        _tag_mode([mesh.nodesTags], name, parameters.get("mode", "append"))
        _append_tag(mesh.nodesTags, name, ids)
    else:
        if isinstance(selector, NodeFilter):
            treatment = parameters.get("treatment", "all")
            if treatment not in ("all", "any"):
                raise ValueError("Node treatment must be all or any")
            selector = ElementFilter(
                nFilter=selector,
                nFilterTreatment="ALL_NODES" if treatment == "all" else "AT_LEAST_ONE",
            )
        selections = [
            (elements, selector.GetIdsToTreat(mesh, elements.elementType))
            for elements, _ in _blocks(mesh, _dimension(parameters))
        ]
        _tag_mode([e.tags for e in mesh.elements], name, parameters.get("mode", "append"))
        for elements, ids in selections:
            _append_tag(elements.tags, name, ids)
    return {"mesh": _publish(mesh)}


def _parameter(name, kind, label, default, options=()):
    return ParameterDefinition(
        name,
        kind,
        label,
        default,
        options=tuple(ParameterOption(value, text) for value, text in options),
    )


def _node(node_id, label, executor, parameters=(), extra_ports=()):
    return NodeDefinition(
        id=node_id,
        label=label,
        icon="mdi-vector-triangle",
        description=label,
        requirements=("py:muscat", "py:numpy"),
        ports=(
            PortDefinition("mesh", PortDirection.INPUT, MESH_DOCUMENT, "Mesh"),
            *extra_ports,
            PortDefinition("mesh", PortDirection.OUTPUT, MESH_DOCUMENT, "Mesh"),
        ),
        parameters=parameters,
        executor=executor,
    )


_ENTITY = _parameter(
    "entity",
    ParameterKind.STR_SELECT,
    "Association",
    "node",
    (("node", "Node"), ("element", "Element")),
)
_FIELD = _parameter("fieldName", ParameterKind.TEXT, "Field name", "")
_DIMENSION = _parameter("dimensionality", ParameterKind.INTEGER, "Dimension (-1: all)", -1)
_TREATMENT = _parameter(
    "treatment",
    ParameterKind.STR_SELECT,
    "Node matching",
    "all",
    (("all", "All nodes"), ("any", "Any node")),
)
_MODES = (("error", "Error if existing"), ("append", "Append"), ("replace", "Replace"))
_CONVERSION_PARAMETERS = (
    _FIELD,
    _parameter("targetName", ParameterKind.TEXT, "Target field (empty: same name)", ""),
    _DIMENSION,
    _parameter("overwrite", ParameterKind.BOOLEAN, "Overwrite target", False),
    _parameter("removeSource", ParameterKind.BOOLEAN, "Remove source field", False),
)

MERGE_MESHES = NodeDefinition(
    id="merge-meshes",
    label="Merge Meshes",
    icon="mdi-vector-union",
    description="Concatenate meshes without welding; union tags and zero-fill missing fields.",
    requirements=("py:muscat", "py:numpy"),
    executor=_merge_meshes,
    ports=(
        PortDefinition(
            "mesh", PortDirection.INPUT, MESH_DOCUMENT, "Mesh", required=False, expandable=128
        ),
        PortDefinition("mesh", PortDirection.OUTPUT, MESH_DOCUMENT, "Merged mesh"),
    ),
)
NODAL_TO_ELEMENT_FIELD = _node(
    "nodal-to-element-field",
    "Nodal Field to Element Field",
    _convert_field(True),
    _CONVERSION_PARAMETERS,
    (PortDefinition("field", PortDirection.OUTPUT, ARRAY, "Converted field"),),
)
ELEMENT_TO_NODAL_FIELD = _node(
    "element-to-nodal-field",
    "Element Field to Nodal Field",
    _convert_field(False),
    _CONVERSION_PARAMETERS,
    (PortDefinition("field", PortDirection.OUTPUT, ARRAY, "Converted field"),),
)
RENAME_MESH_FIELD = _node(
    "rename-mesh-field",
    "Rename Mesh Field",
    _edit_field(True),
    (_ENTITY, _FIELD, _parameter("newName", ParameterKind.TEXT, "New field name", "")),
)
REMOVE_MESH_FIELD = _node(
    "remove-mesh-field", "Remove Mesh Field", _edit_field(False), (_ENTITY, _FIELD)
)
_TAG_PARAMETERS = (
    _parameter("tags", ParameterKind.LIST_STR, "Tags (empty: all)", []),
    _parameter("prefix", ParameterKind.TEXT, "Target tag prefix", ""),
    _DIMENSION,
    _parameter("mode", ParameterKind.STR_SELECT, "Existing target", "error", _MODES),
)
NODE_TAGS_TO_ELEMENT_TAGS = _node(
    "node-tags-to-element-tags",
    "Node Tags to Element Tags",
    _convert_tags(True),
    (*_TAG_PARAMETERS, _TREATMENT),
)
ELEMENT_TAGS_TO_NODE_TAGS = _node(
    "element-tags-to-node-tags", "Element Tags to Node Tags", _convert_tags(False), _TAG_PARAMETERS
)
ADD_TAG = _node(
    "add-tag",
    "Add Tag from Selector",
    _add_tag,
    (
        _parameter("tagName", ParameterKind.TEXT, "Tag name", ""),
        _parameter(
            "entity",
            ParameterKind.STR_SELECT,
            "Tag entity",
            "element",
            (("node", "Node"), ("element", "Element")),
        ),
        _parameter("mode", ParameterKind.STR_SELECT, "Existing tag", "append", _MODES),
        _DIMENSION,
        _TREATMENT,
    ),
    (
        PortDefinition(
            "filter", PortDirection.INPUT, MUSCAT_NODE_FILTER, "Node or element selector"
        ),
    ),
)

MESH_COMPOSITION_NODES = (
    MERGE_MESHES,
    NODE_TAGS_TO_ELEMENT_TAGS,
    ELEMENT_TAGS_TO_NODE_TAGS,
    ADD_TAG,
)
FIELD_COMPOSITION_NODES = (
    NODAL_TO_ELEMENT_FIELD,
    ELEMENT_TO_NODAL_FIELD,
    RENAME_MESH_FIELD,
    REMOVE_MESH_FIELD,
)
