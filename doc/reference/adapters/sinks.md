---
id: reference.adapters.sinks
title: Sink Nodes
section: Reference
order: 19
description: Nodes that consume data in application views.
---

# Sink nodes

## To 3D View (`mesh-sink`)

Requires `mesh: Mesh document` and has no outputs. The node displays the
canonical mesh in the 3D view. UI-only parameters are `color_field=""` (solid
color), `show_representation=True`, and `show_axis_grid=False`. The color-field
menu lists finite numeric nodal fields. Multi-component nodal fields are colored
by their vector magnitude. Elemental fields and direct RGB/RGBA colors are not
yet available in the browser's Plotly surface preview. The WASM runtime returns
triangulated surface coordinates and field values only for connected `mesh-sink`
nodes; it does not serialize the full mesh into the browser.

## Show Image (`local-view`)

Requires one `input: Image` input and has no outputs. After execution, the node displays
the Pillow image in its own embedded viewport. The node has no configurable parameters.

## Show Value (`show-value`)

Accepts `value: Any` and has no outputs. After execution, the node displays the
input's Python `str()` representation on the workflow using the same presentation
style as the Paragraph documentation node. Any value type can be connected to its
input.

## Plot Table (`plot-table`)

Requires `table: Table document` as its only input and has no outputs or
parameters. The workflow view plots numeric list-valued columns in the table;
non-numeric columns are not plotted. Plotting is handled by the presentation,
not by the headless node executor.