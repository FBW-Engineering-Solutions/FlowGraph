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

## ImageJ Groovy Script (`imagej-script`)

Enter a complete Groovy script in the code editor. The node has only the `code`
parameter; SciJava `#@` declarations generate named input and output ports.
For example:

```groovy
#@ Dataset image
#@output Dataset result

result = image
```

## ImageJ Groovy Script File (`imagej-script-file`)

Choose a `.groovy` file with the `filename` parameter, which is also exported
as an optional `FilePath` input port. This node has no code-editor parameter.
Its named inputs and outputs are inferred from the selected file's SciJava `#@`
declarations. An external change to the file requires refreshing the node to
update its visible ports. A filename supplied through the port overrides the
configured filename at execution time; when it refers to a different script,
refresh the node's ports before connecting its script inputs and outputs.

Both ImageJ script nodes use the same Groovy execution and conversion rules:

Image ports (`Dataset`, `Img`, `RandomAccessibleInterval`) carry NumPy
arrays. Common scalar declarations are typed; other types use `Any`. SciJava
service parameters are injected by Fiji and do not appear as graph inputs.
Install the optional extra with `pip install 'flowgraph[imagej]'` and provide a
Java runtime before execution;
Fiji is initialized in headless mode. The first execution may download Fiji
dependencies. These nodes run trusted user code, not a sandbox.