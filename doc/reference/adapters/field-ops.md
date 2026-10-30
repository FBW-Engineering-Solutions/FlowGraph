---
id: reference.adapters.field-ops
title: Field Operation Nodes
section: Reference
order: 17
description: Nodes that extract mesh fields and transfer fields and tags between meshes.
---

# Field-operation nodes

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

- `transferNodeData=True`
- `transferElementData=True`
- `transferNodeTags=False`
- `transferElementTags=False`

FlowGraph-generated ID fields and string fields are not interpolated. The target
mesh is copied before transferred data is written.