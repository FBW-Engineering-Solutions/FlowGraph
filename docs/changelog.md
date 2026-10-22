New in Next :
**********************
**********************

Api Change:
-

New functionalities:
- `flowgraph run` resolves omitted published inputs from compatible saved
  downstream parameter values, including nested workflow inputs and directly
  exported parameters. Each fallback emits a warning to stderr with the input,
  chosen value, and source parameter. Explicit inputs take precedence; missing
  defaults and conflicting downstream values still require explicit inputs.

Corrections:
-

Improvement:
-


New in version 0.1.5:
**********************
**********************

First public release
The `0.1.x` series is alpha. APIs, workflow behavior, and compatibility
guarantees may change before the `1.0.0` stability milestone.

Api Change:
-

New functionalities:
-

Corrections:
-

Improvement:
-
