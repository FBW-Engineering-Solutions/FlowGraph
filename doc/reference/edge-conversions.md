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

The following table lists scalar and path conversions. Vector, array, image,
and selector conversions are described below. Rows are
source-port types and columns are target-port types. An `X` marks an explicitly
registered automatic conversion; a blank cell has no automatic conversion.
Direct connections between compatible types do not require a conversion and are
not marked in this table.

| Source type \ Target type | `Integer` | `Float` | `Text` | `list[int]` | `list[float]` | `FilePath` | `Path` |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `Boolean` | X | X | X |  |  |  |  |
| `Integer` |  | X | X | X |  |  |  |
| `Float` | X |  | X |  | X |  |  |
| `Text` |  |  |  |  |  | X | X |
| `FilePath` |  |  | X |  |  |  |  |
| `Path` |  |  | X |  |  |  |  |

`Boolean → Text` produces exactly `"False"` or `"True"`; `Boolean → Integer`
produces `0` or `1`; and `Boolean → Float` produces `0.0` or `1.0`.
These conversions also normalize configured parameter defaults and overrides.
Reverse conversions to Boolean are not registered.

`Integer → Float` converts the integer to a Python `float`; `Integer → Text`
uses its string representation; and `Integer → list[int]` wraps the value in a
one-item list. `Float → Integer` rounds to the nearest integer, `Float → Text`
uses the float's string representation, and `Float → list[float]` wraps the
value in a one-item list.

`FilePath` (type ID `filename`) and directory `Path` (type ID `dirname`) are
distinct types:

- **Text → FilePath:** construct a `flowgraph.domain.filepath.FilePath` holding
  one primary file path.
- **FilePath → Text:** return the primary path's string representation; dependent
  files are not included in the text.
- **Text → Path:** construct a `pathlib.Path`.
- **Path → Text:** return the path's string representation.

These conversions do not check whether the file or directory exists.

### Vector conversions

All four numeric vector types (`VEC2D`, `VEC3D`, `VEC2DI`, and `VEC3DI`) can
connect to one another. The `I` suffix identifies integer components; the other
two types contain floats.

- **2D → 3D:** append a third component of `0` for integer targets or `0.0` for
  float targets.
- **3D → 2D:** discard the third component.
- **Integer → float:** convert each retained component to a Python `float`.
- **Float → integer:** round each retained component using Python `round`, just
  like the scalar conversion. Halfway values round to the nearest even integer
  (for example, `1.5 → 2`, `2.5 → 2`, and `-2.5 → -2`).

Dimension and component-type changes can happen together. For example,
`VEC2D [1.2, 2.8] → VEC3DI [1, 3, 0]`. Conversions create a new list and leave
the source value unchanged. Numeric vectors must contain exactly two or three
components according to their declared type. Same-type connections need no
conversion. `VEC3D → List Floats` is also registered: it creates a new Python
list without changing the source vector.

Conversions are directional. For example, `Text → Float` is not automatically
accepted. A connection without a direct type match or one of the registered
conversions is rejected; use an explicit workflow node when a different
conversion is required. Conversions are not automatically chained: an edge uses
only the rule registered for its exact source and target type IDs. For example,
`Integer → 1D Array` is not accepted merely because `Integer → Float` and
`Float → 1D Array` are registered.

### Array types and checked conversions

The core exposes three NumPy-array port types from
`flowgraph.adapters.data_types`:

| Constant | Type ID | Display name | Runtime contract |
| --- | --- | --- | --- |
| `ARRAY` | `array` | Array | NumPy array of any rank, including scalar and tensor arrays |
| `ARRAY_1D` | `array-1d` | 1D Array | NumPy array of shape `(n,)` |
| `ARRAY_2D` | `array-2d` | 2D Array | NumPy array of shape `(n, m)` |

These contracts check the container and rank only. Empty arrays and all NumPy
dtypes are permitted; individual nodes decide whether their data must be numeric,
finite, or nonempty. Python lists are not arrays under these contracts.

- Same-type connections and **1D/2D Array → Array** pass the original object
  through unchanged.
- **Array → 1D Array** accepts `(n,)` unchanged or converts `(n, 1)` to a
  one-dimensional view. Other shapes fail at runtime with the received shape.
- **Array → 2D Array** checks that the runtime array is two-dimensional and
  passes it through unchanged; it does not reshape vectors.
- **2D Array → 1D Array** accepts only column arrays `(n, 1)`, exposing `[:, 0]`
  as a view, including for strided arrays. Read-only inputs remain read-only.

Checked connections can be authored before their runtime shape is known.
Multi-component arrays are never silently flattened, and row arrays `(1, n)`
with `n > 1` are not scalar columns. No implicit **1D Array → 2D Array** rule is
provided. Conversions preserve dtype and do not copy array data or modify the
source. Widening rules are also published in the web catalog so ID-based clients
can recognize these connections, although the core needs no conversion for them.

### List and array conversions

`List Floats`, `List Ints`, and the four fixed-size numeric vector types convert
to read-only 1D NumPy arrays. A Float converts to a one-item array. These
sequence conversions allocate array storage; existing arrays use the zero-copy
rules above. A 1D Array converts to `List Floats` (real numeric dtype required)
or `List Any` when a downstream API specifically requires Python lists. Those
conversions allocate lists and leave the source unchanged. No conversions between
these array types and ImageJ NumPy are registered; the image conversion below is
separate.

Wrapped Field and Vector Statistics use 1D Array inputs; Extract Field
outputs generic Array. 1D Array Input (`set-array-1d`) and Plaid time
values output read-only 1D arrays. `LIST_FLOAT` is used for list parameter
editors, explicit user-code `list[float]` annotations and batch list outputs.
Float Batch Workflow inputs accept both float lists and 1D arrays;
array-valued child inputs still represent one value rather than a batch axis.

### Image conversion

**Pillow Image → ImageJ NumPy** (type IDs `image → imagej`) converts a Pillow
image to a detached NumPy array using `np.array(image, copy=True)`. This conversion
allocates array storage and leaves the source image unchanged. The reverse
**ImageJ NumPy → Pillow Image** conversion is not registered.

### Selector conversion

**Element Selector → Node Selector** (type IDs `filter-like → node-filter-like`)
passes the original selector object through unchanged, without copying it.
Element selectors implement the node-selection interface. The reverse
**Node Selector → Element Selector** conversion is not registered.

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