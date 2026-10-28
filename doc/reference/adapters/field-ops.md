---
id: reference.adapters.field-ops
title: Field Operation Nodes
section: Reference
order: 17
description: Nodes that extract mesh fields and transfer fields and tags between meshes.
---

# Field-operation nodes

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