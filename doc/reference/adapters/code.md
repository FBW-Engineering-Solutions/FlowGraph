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

### Editable scalar inputs

Arguments annotated `bool`, `int`, `float`, or `str` also create editable node
parameters: a checkbox, integer field, numeric field, or text field. Their input
ports remain connectable. An upstream connection overrides the configured value
and disables its editor; disconnecting restores the configured fallback. Complex
types such as `MeshDocument`, lists, and `Any` remain connection-only.

```python
def Execute(enabled: bool = True, iterations: int = 10,
            scale: float = 1.0, name: str = "result") -> tuple[str, float]:
    return (name, scale * iterations if enabled else 0.0)
```

Python defaults initialize the controls. Without a default, controls start at
`False`, `0`, `0.0`, or `""`. Scalar defaults must be type-compatible literals,
not expressions or function calls; inspecting a signature never runs user code.
An integer literal is accepted for a float default. Configured values are saved
with the workflow, separately from the source editor, under parameter keys such
as `__user_input__scale`. Editing the signature updates the controls; existing
saved values for unchanged names are retained and must match their current type.

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

Image ports (`ImagePlus`, `Dataset`, `Img`, `RandomAccessibleInterval`) carry NumPy
arrays. Common scalar declarations are typed; other types use `Any`. SciJava
service parameters are injected by Fiji and do not appear as graph inputs.
Install the optional extra with `pip install 'flowgraph[imagej]'` and provide a
Java runtime before execution;
Fiji is initialized in headless mode. The first execution may download Fiji
dependencies. These nodes run trusted user code, not a sandbox.

### Gaussian blur of a Pillow-derived image

An annotated, ready-to-open workflow is included as
`flowgraph/testdata/ImageJBlur.json`. Locate it in an installed environment with
`uv run python -c 'from flowgraph.resources import package_resource_path; print(package_resource_path("testdata", "ImageJBlur.json"))'`.
It uses the bundled image through `{testdata}/ColorCardboard.jpg`, includes
numbered setup/port/conversion notes, a sigma slider and before/after viewers.
It requires native execution with the `io` and `imagej` extras, not browser-only
WASM. Open the JSON in an editor, run it, change sigma and run again.

`IJ.run(image, command, options)` requires an `ImagePlus`, not an ImageJ2
`Dataset`. Declare `ImagePlus` ports to use standard ImageJ1 commands without
manual array-axis handling. Use `Double` for a sigma connected to a Float Slider
(an `Integer` input rounds the slider value):

```groovy
#@ ImagePlus imp
#@ Double sigma
#@output ImagePlus result

import ij.IJ

IJ.run(imp, "Gaussian Blur...", "sigma=" + sigma)
IJ.log("Successfully applied Gaussian Blur with a sigma of: " + sigma)
result = imp
```

Connect `result` to **ImageJ To Pillow**, then connect its `image` output to
**Show Image**. A null image output is reported at the script node; inspect the
Fiji/Groovy error log for script errors rather than changing downstream shapes.

**Read Image (Pillow)** can connect directly to `imp` using the automatic
Pillow-to-NumPy conversion, or through **Pillow To ImageJ**. The bridge constructs
an owned ImageJ1 processor with correct width/height and packed RGB pixels; script
changes do not mutate upstream images. Grayscale uint8, uint16, float32 and uint8
RGB are supported. Returned ImagePlus pixels are read back from the current
processor into height/width or height/width/channel arrays.

ImagePlus input does not silently discard alpha or reduce precision: convert
LA/RGBA to RGB with **Convert Image Mode**, and normalize unsupported dtypes
explicitly. For palette images, convert to RGB first to preserve palette colors.
Stacks and indexed-color ImagePlus outputs are rejected; return a single grayscale
or RGB image. Both `ImagePlus` and fully qualified `ij.ImagePlus` declarations
are supported. Java initialization remains lazy and requires the ImageJ extra.