---
id: reference.adapters.gui
title: GUI Nodes
section: Reference
order: 21
description: Nodes whose values are configured with slider controls.
---

# GUI nodes

| Node (ID) | Output | Parameters/defaults |
| --- | --- | --- |
| **Float Slider** (`float-slider`) | `value: Float` | `min=0.0`, `max=1.0` (optional ports), `value=0.5` |
| **Integer Slider** (`int-slider`) | `value: Integer` | `min=0`, `max=100` (optional ports), `value=50` |

Both sliders require `min < max` and an inclusive `min <= value <= max` range.
Float bounds, values, and output must be finite. The current value is edited in
the node's slider control; connected bound ports override local bounds.