---
id: reference.adapters.controls
title: Control Nodes
section: Reference
order: 21
---

# Control Nodes

Control nodes expose workflow values such as floating-point and integer sliders,
plus headless workflow composition.
Their executors are headless-safe; the GUI uses their `presentation` metadata to
render the corresponding editor.

Available nodes:

- `float-slider`
- `int-slider`
- `run-workflow`
- `batch-workflow`

## Run Full Workflow (`run-workflow`)

Run Full Workflow owns an editable child workflow. Expand the node and click
**Edit workflow** to replace the current Workflow view with that child graph. Build
the child graph normally, then use **Workflow Input** and **Workflow Output** nodes
to publish its external interface. Click **Quit workflow** at the top of the Workflow
view to return to the parent graph.

The composite node dynamically exposes typed ports matching the child workflow's
published inputs and outputs. Values connected to its input ports are supplied to the
child graph, and its output ports carry the corresponding exported values. It also
emits the complete nested `WorkflowRunResult` on `result: Any`, including the nested
execution order and every nested node's retained inputs and outputs. Editing a child
workflow invalidates the composite node and its downstream parent nodes.

## Batch Workflow (`batch-workflow`)

Batch Workflow owns an editable child workflow in the same way as **Run Full
Workflow**, but executes that child once for every item in one or more list
inputs. A scalar child input broadcasts to every execution, while list inputs
are read at the matching index. All supplied list inputs must have the same
length. For example, a child workflow with `int` and `Text` inputs can receive
an integer and a list of text values, a list of integers and a list of text
values, or a list of integers and one text value.

Every published child output is aggregated into an ordered list. The `result`
output is a list of nested `WorkflowRunResult` values. Empty list inputs produce
an empty batch; Batch Workflow rejects execution when no input is a list or when
list inputs have unequal lengths.
