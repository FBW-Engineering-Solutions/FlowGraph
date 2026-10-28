---
id: reference.adapters.vector-tools
title: Vector Tools
section: Reference
order: 23
description: Demand-driven statistics for numeric vectors.
---

# Vector Tools

## Vector Statistics (`vector-statistics`)

Available under **Vector Tools**. Connect a numeric list, fixed-size vector, or
one-dimensional NumPy array to the required `vector` input. The input uses `Any`
to support both lists and arrays (including scalar fields from Extract Field),
and is validated at runtime. Requested calculations require a non-empty vector
of finite real integers or floats; strings, booleans, complex values and
multidimensional arrays are rejected. The input is not modified.

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
inspect the vector or perform any calculation. Direct Python executor calls
must provide `ExecContext(connected_output_ports=...)` to request quantities;
omitting the context requests none. There are no parameters.