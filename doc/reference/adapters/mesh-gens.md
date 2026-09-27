---
id: reference.adapters.mesh-gens
title: Mesh Generation Nodes
section: Reference
order: 14
description: Nodes that construct meshes from non-mesh data.
---

# Mesh-generation nodes

## Table to Mesh (`csv-to-mesh`)

Creates a point mesh from a table. It requires `table: Table` and
`value: List Text` (`Coordinates Names`) and emits `mesh: Mesh document`.
Each named table column supplies one coordinate component; the resulting column
arrays become node fields. The coordinate columns must exist in the table and
have compatible lengths.