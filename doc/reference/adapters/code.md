---
id: reference.adapters.code
title: Code Nodes
section: Reference
order: 22
description: Nodes that execute user-provided code.
---

# Code nodes

## User Function (`user-function`)

The User Function node executes a Python function entered in its multiline code
editor. The editor uses locally bundled CodeMirror 5 with Python syntax
highlighting, line numbers, indentation, line wrapping, and bracket matching.
The source must define one regular `Execute` function. Its positional parameter
names become optional input ports on that node. Its fixed-length `tuple[...]`
return annotation determines the number and types of generated output ports.
Use no annotation (or `Any`) for an `Any` port, or annotate parameters with
`str`, `bool`, `int`, `float`, `list[str]`, `list[int]`, or `list[float]` to
create a typed input or output. For example:

```python
def Execute(name: str, scale: float) -> tuple[str, float]:
    return (name.upper(), scale * 2)
```

This creates `name: Text` and `scale: Float` inputs plus `output1: Text` and
`output2: Float`. Use `tuple[()]` for no outputs. The runtime requires the
returned tuple length and values to match the declared output ports.

The Web Editor checks this declaration without executing it and updates the node
ports as the source changes.

This is trusted local Python execution, not a sandbox. Changing the code marks
the node and all downstream nodes invalid until they are run again.