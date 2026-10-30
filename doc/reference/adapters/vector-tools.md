---
id: reference.adapters.vector-tools
title: Vector Tools
section: Reference
order: 23
description: Indexed value extraction and demand-driven statistics for numeric vectors.
---

# Vector Tools

## Scalars to 1D Array (`scalars-to-array-1d`)

Connect scalar outputs to the expandable `scalar: Float` input family, with up
to **125** numbered ports (`scalar_1` through `scalar_125`). One spare input is
shown as connections are added, until the limit is reached. Integer outputs use
the existing Float conversion.

The `array: 1D Array` output is a read-only NumPy float64 array containing only
connected values in numeric port order, not connection creation order. Gaps are
omitted, not filled with zeros. For example, `scalar_1 = 10`, `scalar_3 = 30`
produces `[10.0, 30.0]`. With no connected inputs the result has shape `(0,)`.
NaN and infinity values are preserved. Building the array allocates its storage
once; no additional output copy is made. There are no parameters.

## Extract Vector Value (`extract-vector-value`)

Extract one component from the required `vector: 1D Array` input, returning
`value: Float`. Configure the integer `index` parameter (default `0`), or connect
an Integer output to its optional input port to override the local setting.
Indices are zero-based: `0` selects the first value, `1` the second, and `-1`
the last. For example, `[10, 20, 30]` with index `1` returns `20.0`.

Numeric list and fixed-size vector ports use the existing array conversions.
Generic Array inputs are rank-checked by those conversions; `(n, 1)` columns
become zero-copy 1D views. Empty vectors, multi-component arrays, non-real data,
and out-of-range indices produce errors. The node does not copy or modify an
input array; only the selected scalar is converted to a Python float. Integer
values therefore follow Float precision, and selected NaN/infinity values are
preserved (JSON results represent non-finite numbers as null).

## Vector Statistics (`vector-statistics`)

Available under **Vector Tools**. Connect a numeric list, fixed-size vector, or
one-dimensional NumPy array to the required `vector: 1D Array` input. Numeric
list/vector ports use registered array conversions. Generic Array outputs
(including Extract Field) are checked at runtime; `(n, 1)` columns become `(n,)`
views. Requested calculations require a non-empty vector
of finite real integers or floats; strings, booleans, complex values and
multi-component arrays are rejected. The input is not modified.

| Output | Type | Meaning |
| --- | --- | --- |
| `min` | Float | Minimum value |
| `min_index` | Integer | Zero-based index of the first minimum |
| `max` | Float | Maximum value |
| `max_index` | Integer | Zero-based index of the first maximum |
| `mean` | Float | Arithmetic mean |
| `std` | Float | Population standard deviation (`ddof=0`) |

Only connected outputs are calculated. Exported workflow outputs also count as
connected. An extremum and its index share one search when both are requested.
Mean and standard deviation use float64 accumulation. For a single value,
standard deviation is zero and both indices are zero.

The engine requires all declared outputs to exist: unconnected value outputs
contain `NaN`, and unconnected index outputs contain `-1`. These are unused
markers, not computed statistics. With no connected outputs, the node does not
inspect the vector or perform any calculation within its executor (the engine
still validates/converts connected inputs). Direct Python executor calls
must provide `ExecContext(connected_output_ports=...)` to request quantities;
omitting the context requests none. There are no parameters.