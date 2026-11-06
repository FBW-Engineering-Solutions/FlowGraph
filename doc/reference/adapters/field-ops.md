---
id: reference.adapters.field-ops
title: Field Operation Nodes
section: Reference
order: 17
description: Nodes that extract mesh fields and transfer fields and tags between meshes.
---

# Field-operation nodes

## Vector Field Gradient (`vector-field-gradient`)

Uses the same inputs, settings, selector semantics and Muscat derivative/recovery
APIs as Scalar Field Gradient below, but `fieldName` selects a finite real nodal
vector of shape `(N,2)` or `(N,3)`. The vector component count need not equal the
mesh coordinate dimension (for example, three-component displacement on a 2D
mesh). Scalar, tensor, boolean, complex, nonfinite and misaligned fields fail.

Outputs `mesh` plus read-only `gradient: 2D Array`, shared with the attached
`<fieldName>_gradient` field (or `targetName`). The Jacobian is flattened into
shape `(entities, components * coordinate_dimensions)` in **component-major**
order: column `i * dimension + j` contains `d(vector_i)/d(x_j)`. For a 3D vector
on a 3D mesh the nine columns are:

```text
du_x/dx, du_x/dy, du_x/dz,
du_y/dx, du_y/dy, du_y/dz,
du_z/dx, du_z/dy, du_z/dz
```

Reshape an array row to `(components, coordinate_dimensions)` for its gradient
matrix; the flattened layout works with existing mesh field and VTK projection
APIs. The result is the full gradient, not a symmetrized strain tensor.

Choose `entity="node"` (default) or `"element"` for Cells / Elements. An optional
element selector controls which elements contribute; absent one, only the highest
dimension is used. Mixed dimensions and point elements fail, empty selections
produce zeros, and excluded cells/unreferenced nodes receive zero. Cell output
uses Muscat's mean IP representation, node output its multiplicity-weighted
IP-to-node recovery, independently for each component and coordinate derivative.
Existing-field conflicts require `overwrite=True`; reserved IDs are protected.
Inputs and original metadata remain unchanged, with read-only output views.

## Scalar Field Gradient (`scalar-field-gradient`)

Select a scalar **node** field by its exact `fieldName`. Requires `mesh: Mesh
document`; an optional `filter: Element selector` restricts the contributing
elements. Without a selector, only the highest-dimensional elements are used.

| Parameter | Default / meaning |
| --- | --- |
| `fieldName` | `""`; required scalar node field name |
| `entity` | `"node"`: Nodes, or `"element"`: Cells / Elements |
| `targetName` | `""`; empty uses `<fieldName>_gradient` |
| `overwrite` | `False`; permit replacing an existing output field |

Outputs the updated `mesh` and a read-only `gradient: 2D Array`, sharing the
attached vector field. Rows follow the full node or global element ordering;
columns are derivatives in coordinate order (one per mesh coordinate dimension).
Unselected cells and nodes without contributing elements receive zero.

All numerical computation uses Muscat: `NodeFieldToFEField`, followed by
`TransferFEFieldToIPField` for each coordinate derivative. Cell output uses
`GetCellRepresentation()` (the arithmetic mean of integration-point derivatives).
Node output uses `GetIpFieldRepresentation().GetPointRepresentation()` with
Muscat's default multiplicity weighting: local IP-to-node recovery, then equal
weight per contributing element. This is not a custom volume-weighted recovery
or a cell average of already-smoothed nodal gradients.

Accepts finite real integer/float scalars of shape `(N,)` or `(N,1)` aligned with
the mesh nodes. Vector, complex, boolean, nonfinite and misaligned fields fail.
Selections must contain a single element dimension (1, 2 or 3); mixed dimensions
and point elements fail. An empty selection produces a zero field. Supported
element spaces, quadrature and embedded-element derivative behavior are Muscat's;
degenerate elements may fail in its FE routines. Geometry, existing fields,
tags and IDs are preserved through read-only views; upstream inputs are unchanged.
Reserved FlowGraph ID fields cannot be differentiated or overwritten.

## Field association conversion

- **Nodal Field to Element Field** (`nodal-to-element-field`) computes the
  arithmetic mean of values at each element's nodes.
- **Element Field to Nodal Field** (`element-to-nodal-field`) computes the equally
  weighted mean of incident element values at each node. Unreferenced nodes get
  zero. This is not volume-weighted, conservative, or an inverse of nodal averaging.

Both require `mesh: Mesh document`, and emit an updated `mesh` plus the converted
read-only `field: Array`. They convert a named mesh field, not an arbitrary array;
use Set Mesh Field first to attach an array. Connectable settings:

| Parameter | Default / meaning |
| --- | --- |
| `fieldName` | `""`; required source field name |
| `targetName` | `""`; empty uses the source name in the other association |
| `dimensionality` | `-1`: all elements, or select 0–3 |
| `overwrite` | `False`; allow replacing an existing destination field |
| `removeSource` | `False`; remove the source only from the output mesh |

Scalar `(n,)` and multi-component `(n,c)` integer/float/complex fields are accepted.
Averages promote to at least float64 (complex remains complex); nonfinite values
propagate. Boolean, text, object, tensor-rank and mismatched-length fields fail.
Arrays remain full-sized: excluded elements and nodes with no contributing
selected elements receive zero. Selecting all dimensions includes boundary and
volume elements together; select a dimension when that would bias node averages.
Original fields, geometry, tags and IDs are retained unless source removal is
requested. Reserved FlowGraph ID fields cannot be converted or overwritten.

## Rename / Remove Mesh Field

**Rename Mesh Field** (`rename-mesh-field`) and **Remove Mesh Field**
(`remove-mesh-field`) require and emit `mesh: Mesh document`. Connectable settings
are `entity="node"` (or `"element"`) and `fieldName=""`; Rename also requires
`newName=""`. Missing fields, empty names and reserved FlowGraph IDs fail.
Rename rejects existing destination names (renaming to the same name is a no-op).
Only the output field dictionary changes: unchanged array storage is shared
through read-only views and upstream inputs remain unchanged.

## Set Mesh Field (`set-mesh-field`)

Requires `mesh: Mesh document` and `field: Array`; outputs `mesh: Mesh document`.
Connectable parameters are `fieldName="field"` and `entity="node"` (Node or
Element). A field must be a 1D scalar or 2D multi-component array whose first
dimension matches the selected entity count. Names are nonempty and case-sensitive.
Existing fields may be replaced, except reserved `flowgraph_node_id` and
`flowgraph_element_id`. No interpolation or dtype conversion is performed.

The output mesh has independent metadata with read-only views of field and mesh
arrays; data storage is shared without copying. Upstream owners must not mutate
shared arrays after publishing them. This completes the workflow
**Extract Field → Calculator → Set Mesh Field → Write Mesh**.

## Extract Field (`extract-field`)

Available under **Mesh Tools → Field Ops**. Requires `mesh: Mesh document`;
emits `field: Array`, containing an independent NumPy array. Parameters are
`entity="node"` (Association: Node or Element) and `fieldName=""` (the exact,
case-sensitive field name). Both parameters are also optional input ports;
connected values override their local settings.

Scalar, vector, tensor, integer and text fields retain their original shape,
dtype and mesh ordering. Element fields use the mesh's global element ordering;
no interpolation or component reduction is performed. The returned array does
not share storage with the mesh field. Missing fields report the association,
requested name and available fields; empty names and unknown associations fail.

Connect this output directly to Wrapped Field or Vector Statistics. Their
1D Array inputs accept scalar `(n,)` fields or normalize `(n, 1)` column fields
without another data copy. Multi-component/tensor connections can be authored,
but fail at runtime with their received shape rather than flattening components.

## Transfer Fields (`transfer-fields`)

Requires `source_data: Mesh document` and `target: Mesh document`; emits
`mesh_document: Mesh document`. It interpolates source node and element fields
onto the target mesh. Parameters are UI-only and default to:

- `method="Interp/Clamp"` (Interpolation / Clamp, or inter-clamp)
- `transferNodeData=True`
- `transferElementData=True`
- `transferNodeTags=False`
- `transferElementTags=False`

The **Interpolation** dropdown controls both field and tag transfers, for nodes
and elements. **Interpolation / Clamp** interpolates inside the source mesh and
uses the closest point on its boundary outside. Other choices are
**Interpolation / Nearest**, **Interpolation / Extrapolation**,
and **Interpolation / Zero Fill**. Workflows without a saved method use
Interpolation / Clamp.

FlowGraph-generated ID fields and string fields are not interpolated. The output
uses a view of the target mesh, sharing its geometry without a full mesh copy.