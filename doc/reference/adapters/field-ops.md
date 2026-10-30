---
id: reference.adapters.field-ops
title: Field Operation Nodes
section: Reference
order: 17
description: Nodes that extract mesh fields and transfer fields and tags between meshes.
---

# Field-operation nodes

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