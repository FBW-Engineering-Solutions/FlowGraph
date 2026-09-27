---
id: reference.edge-conversions
title: Edge Conversions
section: Reference
order: 11
description: Understand automatic type conversions on workflow connections.
---

# Edge conversions

An edge connects an output port on one workflow node to an input port on another.
Normally, both ports must have compatible data types. FlowGraph can also accept a
connection when it has an explicitly registered, directed automatic conversion.

## Available conversions

FlowGraph currently provides the following automatic conversions. Rows are
source-port types and columns are target-port types. An `X` marks an explicitly
registered automatic conversion; a blank cell has no automatic conversion.
Direct connections between compatible types do not require a conversion and are
not marked in this table.

| Source type \ Target type | `Integer` | `Float` | `Text` | `list[int]` | `list[float]` | `Path` |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| `Integer` |  | X | X | X |  |  |
| `Float` | X |  | X |  | X |  |
| `Text` |  |  |  |  |  | X |
| `Path` |  |  | X |  |  |  |

`Integer → Float` converts the integer to a Python `float`; `Integer → Text`
uses its string representation; and `Integer → list[int]` wraps the value in a
one-item list. `Float → Integer` rounds to the nearest integer, `Float → Text`
uses the float's string representation, and `Float → list[float]` wraps the
value in a one-item list. `filename → Text` and `Text → filename` preserve the
value as text while changing its workflow port type.

Conversions are directional. For example, `Text → Float` is not automatically
accepted. A connection without a direct type match or one of the registered
conversions is rejected; use an explicit workflow node when a different
conversion is required.

## Using a converted connection

Connect ports normally in the **Workflow** panel. When FlowGraph applies an
automatic conversion:

- the connection is shown in amber instead of the standard edge color;
- selecting the edge in the workflow displays its endpoints and conversion in
  the **Node Inspector**; and
- during execution, the target node receives the converted value, validated
  against its input port type.

For example, an **Integer Input** value of `4` connected to a `Float` input
delivers `4.0` to the target node. Connecting that float to a `Text` input then
delivers `"4.0"`.

The inspector's transported value is the source output retained by the workflow
run result. The `Conversion` line identifies the transformation applied before
the value reaches the target input.

## Extending conversion rules

Conversion rules are defined centrally in
`flowgraph.application.port_conversions`. Each rule has stable source and target
type IDs, a human-readable label, and a conversion callable. Add only deliberate,
directed conversions: implicit lossy or ambiguous casts should remain explicit
workflow operations.

Workflow JSON stores only edge endpoints. The applicable conversion is resolved
from the current source and target port types, so it is applied consistently by
validation, execution, edge rendering, and the Node Inspector.