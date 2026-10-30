"""Non-mutating Muscat mesh inspection, cleanup, and field attachment nodes."""

from collections.abc import Mapping
from typing import Any

import numpy as np
from Muscat.LinAlg.MatVecOperations import ImmutableView
from Muscat.MeshContainers import ElementsDescription as ED
from Muscat.MeshContainers.ElementsContainers import AllElements, ElementsContainer
from Muscat.MeshContainers.Filters.FilterObjects import ElementFilter
from Muscat.MeshTools.MeshInspectionTools import GetMeasure, GetVolumePerElement
from Muscat.MeshTools.MeshModificationTools import (
    CleanDoubleElements,
    CleanDoubleNodes,
    ComputeSkin,
)
from Muscat.MeshTools.MeshTools import GetElementsCenters
from Muscat.Types import MuscatIndex

from flowgraph.adapters.data_types import (
    ARRAY,
    ARRAY_1D,
    ARRAY_2D,
    FLOAT,
    MESH_DOCUMENT,
    MUSCAT_ELEMENT_FILTER,
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


def _result(mesh):
    """Publish a read-only mesh view, with validated FlowGraph IDs."""
    return {"mesh": MeshDocument(MeshDocument(mesh).mesh.View())}


def _editable_elements(source):
    """Detach container metadata without copying unchanged array storage."""
    mesh = source.View()
    mesh.elements = AllElements()
    for original in source.elements:
        elements = ElementsContainer(original.elementType)
        elements.connectivity = ImmutableView(original.connectivity)
        elements.originalIds = ImmutableView(original.originalIds)
        elements.cpt = original.GetNumberOfElements()
        elements.tags = original.tags.View()
        mesh.elements.AddContainer(elements)
    return mesh


def _set_field(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Attach a scalar/vector field through a read-only view without copying data."""
    source = inputs["mesh"].mesh
    entity = parameters.get("entity", "node")
    if entity not in ("node", "element"):
        raise ValueError("Field association must be 'node' or 'element'")
    name = parameters.get("fieldName", "field")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Field name must be a nonempty string")
    if name in ("flowgraph_node_id", "flowgraph_element_id"):
        raise ValueError("Cannot overwrite reserved FlowGraph ID fields")
    data = inputs["field"]
    count = source.GetNumberOfNodes() if entity == "node" else source.GetNumberOfElements()
    if not isinstance(data, np.ndarray) or data.ndim not in (1, 2):
        raise ValueError("Field must be a 1D or 2D NumPy array")
    if len(data) != count:
        raise ValueError(f"Field length must match {entity} count ({count})")
    mesh = source.View()
    fields = mesh.nodeFields if entity == "node" else mesh.elemFields
    fields[name] = ImmutableView(data)
    return _result(mesh)


def _skin(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Extract boundary elements, retaining nodal metadata and generating boundary IDs."""
    source = inputs["mesh"].mesh
    dim = parameters.get("dimensionality", -1)
    if isinstance(dim, bool) or not isinstance(dim, int) or dim not in (-1, 1, 2, 3):
        raise ValueError("Skin dimensionality must be -1 (automatic), 1, 2, or 3")
    if not source.GetNumberOfElements():
        raise ValueError("Skin extraction requires elements of dimension at least 1")
    dim = source.GetElementsDimensionality() if dim == -1 else dim
    if dim < 1:
        raise ValueError("Skin extraction requires elements of dimension at least 1")
    mesh = ComputeSkin(source.View(), md=dim, inPlace=False)
    mesh.nodeFields = source.View().nodeFields
    mesh.elemFields = {}
    return _result(mesh)


def _measure(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Measure a single-dimensional selection, defaulting to the highest dimension."""
    mesh = inputs["mesh"].mesh.View()
    if not mesh.GetNumberOfElements():
        return {"measure": 0.0}
    selector = inputs.get("filter")
    if selector is None:
        selector = ElementFilter(dimensionality=mesh.GetElementsDimensionality())
    dimensions = {ED.dimensionality[s.elementType] for s in selector(mesh) if s.Size()}
    if len(dimensions) > 1:
        raise ValueError("Mesh Measure cannot combine mixed-dimensional selections")
    return {"measure": float(GetMeasure(mesh, selector)) if dimensions else 0.0}


def _element_measures(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Return selected measures paired with global positional element indices."""
    mesh = inputs["mesh"].mesh.View()
    selector = inputs.get("filter", ElementFilter())
    indices = np.concatenate(
        [s.meshOffset + s.indices for s in selector(mesh)] + [np.empty(0, dtype=MuscatIndex)]
    ).astype(MuscatIndex, copy=False)
    # Evaluate all elements in canonical global order, then gather the selection.
    # This avoids relying on backend-specific filtered DOF numbering.
    values = GetVolumePerElement(mesh)[indices] if len(indices) else np.empty(0)
    return {"measures": ImmutableView(values), "indices": ImmutableView(indices)}


def _centers(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Return arithmetic element centers in canonical global element order."""
    return {"centers": ImmutableView(GetElementsCenters(inputs["mesh"].mesh))}


def _merge_nodes(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Merge nearby nodes while retaining representative node fields and IDs."""
    source = inputs["mesh"].mesh
    tolerance = parameters.get("tolerance", 0.0)
    if isinstance(tolerance, bool) or not np.isscalar(tolerance):
        raise ValueError("Tolerance must be a finite nonnegative number")
    tolerance = float(tolerance)
    if not np.isfinite(tolerance) or tolerance < 0:
        raise ValueError("Tolerance must be a finite nonnegative number")
    mesh = _editable_elements(source)
    kept = None
    if source.GetNumberOfNodes():
        kept = CleanDoubleNodes(mesh, tol=tolerance, propagateToNodeFields=True)
    if kept is None:
        kept = np.arange(source.GetNumberOfNodes(), dtype=MuscatIndex)
    return {**_result(mesh), "indices": ImmutableView(kept)}


def _remove_elements(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Remove duplicate connectivity, merging tags and keeping first-element fields."""
    mesh = _editable_elements(inputs["mesh"].mesh)
    CleanDoubleElements(mesh)
    return _result(mesh)


def _input(name, kind, required=True):
    return PortDefinition(
        name, PortDirection.INPUT, kind, name.replace("_", " ").title(), required=required
    )


def _output(name, kind):
    return PortDefinition(name, PortDirection.OUTPUT, kind, name.title())


def _node(node_id, label, executor, ports, parameters=()):
    return NodeDefinition(
        id=node_id,
        label=label,
        icon="mdi-vector-triangle",
        description=executor.__doc__ or label,
        requirements=("py:muscat", "py:numpy"),
        ports=ports,
        parameters=parameters,
        executor=executor,
    )


SET_MESH_FIELD = _node(
    "set-mesh-field",
    "Set Mesh Field",
    _set_field,
    (_input("mesh", MESH_DOCUMENT), _input("field", ARRAY), _output("mesh", MESH_DOCUMENT)),
    (
        ParameterDefinition("fieldName", ParameterKind.TEXT, "Field name", "field"),
        ParameterDefinition(
            "entity",
            ParameterKind.STR_SELECT,
            "Association",
            "node",
            options=(ParameterOption("node", "Node"), ParameterOption("element", "Element")),
        ),
    ),
)
EXTRACT_SKIN = _node(
    "extract-skin",
    "Extract Skin",
    _skin,
    (_input("mesh", MESH_DOCUMENT), _output("mesh", MESH_DOCUMENT)),
    (
        ParameterDefinition(
            "dimensionality", ParameterKind.INTEGER, "Source dimension (-1: automatic)", -1
        ),
    ),
)
MESH_MEASURE = _node(
    "mesh-measure",
    "Mesh Measure",
    _measure,
    (
        _input("mesh", MESH_DOCUMENT),
        _input("filter", MUSCAT_ELEMENT_FILTER, False),
        _output("measure", FLOAT),
    ),
)
ELEMENT_MEASURES = _node(
    "element-measures",
    "Element Measures",
    _element_measures,
    (
        _input("mesh", MESH_DOCUMENT),
        _input("filter", MUSCAT_ELEMENT_FILTER, False),
        _output("measures", ARRAY_1D),
        _output("indices", ARRAY_1D),
    ),
)
ELEMENT_CENTERS = _node(
    "element-centers",
    "Element Centers",
    _centers,
    (_input("mesh", MESH_DOCUMENT), _output("centers", ARRAY_2D)),
)
MERGE_DUPLICATE_NODES = _node(
    "merge-duplicate-nodes",
    "Merge Duplicate Nodes",
    _merge_nodes,
    (_input("mesh", MESH_DOCUMENT), _output("mesh", MESH_DOCUMENT), _output("indices", ARRAY_1D)),
    (ParameterDefinition("tolerance", ParameterKind.FLOAT, "Tolerance", 0.0),),
)
REMOVE_DUPLICATE_ELEMENTS = _node(
    "remove-duplicate-elements",
    "Remove Duplicate Elements",
    _remove_elements,
    (_input("mesh", MESH_DOCUMENT), _output("mesh", MESH_DOCUMENT)),
)

MESH_NODES = (
    EXTRACT_SKIN,
    MESH_MEASURE,
    ELEMENT_MEASURES,
    ELEMENT_CENTERS,
    MERGE_DUPLICATE_NODES,
    REMOVE_DUPLICATE_ELEMENTS,
)
