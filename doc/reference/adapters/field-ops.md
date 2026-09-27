---
id: reference.adapters.field-ops
title: Field Operation Nodes
section: Reference
order: 17
description: Nodes that transfer mesh fields and tags between meshes.
---

# Field-operation nodes

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