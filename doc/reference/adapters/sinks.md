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
menu lists named point and cell arrays with one to four components. One-component
arrays use scalar lookup-table coloring; two-, three-, and four-component arrays
use VTK direct colors, supporting luminance/alpha, RGB, and RGBA fields such as
`Colors`.

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