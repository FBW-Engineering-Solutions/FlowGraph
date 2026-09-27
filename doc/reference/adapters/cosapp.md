---
id: reference.adapters.cosapp
title: CoSApp
section: Reference
order: 24
description: Execute externally authored CoSApp System models from a FlowGraph node.
---

# CoSApp nodes

Install the optional integration before running these nodes:

```bash
uv sync --extra cosapp
```

## CoSApp Workflow

**CoSApp Workflow** (`cosapp-workflow`) executes an externally authored, trusted
Python CoSApp model. It always emits `result`, the executed root
`cosapp.base.System`. Its additional `Any` inputs and outputs are generated from
the JSON mappings entered in **Input paths** and **Output paths**.

The selected Python file must define a zero-argument factory, named
`create_model` by default, that returns the root `System`. FlowGraph creates a
fresh model for every execution, assigns each connected input to its configured
dot path, calls `run_drivers()`, and then reads every configured output path.

For example, a CoSApp circuit factory might return the tutorial's root `p`.
Configure these paths to expose its computed values:

```json
{
  "node_1_voltage": "circuit.n1.V",
  "resistor_1_current": "circuit.R1.I.I",
  "diode_current": "circuit.D1.I.I"
}
```

Nested port fields are supported, so `circuit.R1.I.I` reads the `I` field of the
resistor's `Intensity` port. Paths must contain dot-separated Python identifiers.
The output name `result` is reserved for the root CoSApp system.

The external file is imported and executed as trusted local Python. Do not run
models from untrusted sources.