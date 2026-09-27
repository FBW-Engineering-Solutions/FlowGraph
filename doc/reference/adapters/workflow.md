---
id: reference.adapters.workflow
title: Workflow
section: Reference
order: 23
description: Nodes that define a workflow's public inputs and outputs.
---

# Workflow nodes

The **Workflow** menu contains the orange boundary nodes used to define the
public interface of a workflow.

## Workflow Input

**Workflow Input** (`workflow-input`) has an editable **Input name** text field, an `Any` input, and
an `Any` output. The text field becomes the public workflow input name. Values
provided when executing the workflow enter through the node's input and leave
through its output for downstream connections.

When the output is connected inside the workflow, FlowGraph automatically infers
the public input type from its destinations. If one type can safely feed every
destination directly or through a registered conversion, parent workflows expose
that type. Unconnected or incompatible destinations remain `Any`.

## Workflow Output

**Workflow Output** (`workflow-output`) has an editable **Output name** text field and an `Any` input.
The text field becomes the public workflow output name. Connect an upstream value
to the node to publish that value when the workflow executes.

FlowGraph automatically exports the type of the connected upstream output. This
typed interface is propagated to parent **Run Full Workflow** nodes, preventing
incompatible parent connections before execution.

Names must be non-empty and unique within their respective input or output list.