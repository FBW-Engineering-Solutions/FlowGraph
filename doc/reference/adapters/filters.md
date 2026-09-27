---
id: reference.adapters.filters
title: Filter Nodes
section: Reference
order: 15
description: Nodes that create and apply Muscat element filters.
---

# Filter nodes

## Element Selector (`create-muscat-element-filter`)

Creates `filter: Element filter`. Parameters (all default to `[]`) are
`dimensionality` (choices 0–3), `element_types` (Muscat element-type names),
`ntag` (node-tag names), and `etag` (element-tag names). Each parameter is also
an optional input port. Empty selections mean no restriction for that criterion.

## Filter Mesh (`filter-mesh-muscat`)

Requires `mesh: Mesh document` and `filter: Element filter`; emits
`mesh: Mesh document` containing the selected elements. Node fields are retained
on the filtered result. The operation extracts a new document and does not
change the input document.