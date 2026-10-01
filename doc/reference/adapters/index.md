---
id: reference.adapters
title: Adapter Node Catalog
section: Reference
order: 11
description: Reference for every node exposed by each FlowGraph adapter group.
---

# Adapter node catalog

Adapter groups provide the built-in nodes shown in the **Nodes** menu. Each page
below documents every node in one group, including its stable definition ID,
connection ports, parameters, defaults, and important runtime behavior.
For definitions created in your own Python code, see
[Create and Run Python Nodes](../../user-guide/custom-nodes.md).

- [Inputs](inputs.md)
- [Files](file.md)
- [Readers](readers.md)
- [Mesh Gens](mesh-gens.md)
- [Mesh Creation](mesh-creation-tools.md)
- [Filters](filters.md)
- [Mesh Ops](mesh-ops.md)
- [Field Ops](field-ops.md)
- [File Conversion](file-conversion.md)
- [Writers](writers.md)
- [Sinks](sinks.md)
- [Doc](doc.md)
- [GUI](gui.md)
- [Controls](controls.md)
- [Image Tools](image-tools.md)
- [Table Tools](table-tools.md)
- [Code](code.md)
- [Workflow](workflow.md)
- [External Tools → CoSApp](cosapp.md)
- [External Tools → Plaid](plaid.md)

Plaid nodes are available only when the Plaid package can be imported. The
reference remains available when the optional dependency is not installed.

CoSApp nodes require the optional `cosapp` dependency. Install it with
`uv sync --extra cosapp`.