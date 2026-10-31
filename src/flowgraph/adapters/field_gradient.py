"""Scalar nodal field derivatives using Muscat's FE/IP field representations."""

import numpy as np
from Muscat.FE.Fields.FieldTools import NodeFieldToFEField, TransferFEFieldToIPField
from Muscat.MeshContainers import ElementsDescription as ED
from Muscat.MeshContainers.Filters.FilterObjects import ElementFilter

from flowgraph.adapters.data_types import (
    ARRAY_2D,
    MESH_DOCUMENT,
    MUSCAT_ELEMENT_FILTER,
    ParameterKind,
)
from flowgraph.adapters.mesh_analysis import _editable_elements
from flowgraph.adapters.mesh_composition import _field_name, _fields, _publish
from flowgraph.application.workflow_core import (
    NodeDefinition,
    ParameterDefinition,
    ParameterOption,
    PortDefinition,
    PortDirection,
)


def _gradient(inputs, parameters, _exec_context=None):
    """Differentiate a scalar node field on selected elements using Muscat."""
    source = inputs["mesh"].mesh
    name = _field_name(parameters.get("fieldName", ""))
    if name not in source.nodeFields:
        raise ValueError(f"Scalar node field {name!r} does not exist")
    scalar = source.nodeFields[name]
    if (
        scalar.shape not in ((source.GetNumberOfNodes(),), (source.GetNumberOfNodes(), 1))
        or scalar.dtype.kind not in "iuf"
        or not np.isfinite(scalar).all()
    ):
        raise ValueError("Source must be a finite real scalar node field of shape (N,) or (N, 1)")
    entity = parameters.get("entity", "node")
    destination = _fields(source, entity)
    target = _field_name(parameters.get("targetName", "") or f"{name}_gradient")
    if target in destination and not parameters.get("overwrite", False):
        raise ValueError(f"Destination field {target!r} already exists")

    # Muscat FE routines cache numbering/offset metadata. Detach containers, not
    # geometry/fields, so backend bookkeeping cannot change the upstream mesh.
    mesh = _editable_elements(source)
    selector = inputs.get("filter")
    if selector is None:
        selector = ElementFilter(dimensionality=mesh.GetElementsDimensionality())
    dimensions = {ED.dimensionality[s.elementType] for s in selector(mesh) if s.Size()}
    if len(dimensions) > 1 or 0 in dimensions:
        raise ValueError("Gradient requires a single element dimension of 1, 2, or 3")
    count = mesh.GetNumberOfNodes() if entity == "node" else mesh.GetNumberOfElements()
    values = np.zeros((count, mesh.GetPointsDimensionality()))
    if dimensions:
        field = NodeFieldToFEField(mesh, {"scalar": scalar.reshape(-1)})["scalar"]
        for axis in range(values.shape[1]):
            derivative = TransferFEFieldToIPField(field, der=axis, elementFilter=selector)
            if entity == "element":
                values[:, axis] = derivative.GetCellRepresentation()
            else:
                values[:, axis] = derivative.GetIpFieldRepresentation().GetPointRepresentation(
                    elementFilter=selector
                )
    _fields(mesh, entity)[target] = values
    document = _publish(mesh)
    return {"mesh": document, "gradient": _fields(document.mesh, entity)[target]}


SCALAR_FIELD_GRADIENT = NodeDefinition(
    id="scalar-field-gradient",
    label="Scalar Field Gradient",
    icon="mdi-vector-line",
    description="Compute a scalar node field gradient on selected elements, at nodes or cells.",
    requirements=("py:muscat", "py:numpy"),
    ports=(
        PortDefinition("mesh", PortDirection.INPUT, MESH_DOCUMENT, "Mesh"),
        PortDefinition(
            "filter", PortDirection.INPUT, MUSCAT_ELEMENT_FILTER, "Element selector", required=False
        ),
        PortDefinition("mesh", PortDirection.OUTPUT, MESH_DOCUMENT, "Mesh"),
        PortDefinition("gradient", PortDirection.OUTPUT, ARRAY_2D, "Gradient"),
    ),
    parameters=(
        ParameterDefinition("fieldName", ParameterKind.TEXT, "Scalar node field", ""),
        ParameterDefinition(
            "entity",
            ParameterKind.STR_SELECT,
            "Output association",
            "node",
            options=(
                ParameterOption("node", "Nodes"),
                ParameterOption("element", "Cells / Elements"),
            ),
        ),
        ParameterDefinition(
            "targetName", ParameterKind.TEXT, "Output field (empty: source_gradient)", ""
        ),
        ParameterDefinition("overwrite", ParameterKind.BOOLEAN, "Overwrite target", False),
    ),
    executor=_gradient,
)
