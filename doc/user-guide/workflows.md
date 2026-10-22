---
id: user-guide.workflows
title: Workflows
section: User Guide
order: 25
description: Build, save, and execute reusable FlowGraph workflows.
---

# Workflows

A FlowGraph workflow is a directed graph of typed nodes. Each node performs one
step, such as selecting a file, reading data, transforming it, displaying a
result, or writing it to disk. Connections pass values from a named output port
to a named input port. The workflow engine is domain-independent: mesh and image
operations are examples of adapter-provided nodes, not limits on the workflow
model.

Pillow image workflows are supported by the Image Tools adapter. It can read,
transform, display, and write images, while the mesh adapters provide the
finite-element workflow capabilities described below.

For example, a mesh conversion workflow can be arranged as:

```text
Select file ── path (Text) ──▶ Read Mesh (Muscat)
                                   │ mesh (Mesh document)
                                   ├────────▶ To 3D View
                                   └────────▶ Write Mesh (MeshIO)
```

The mesh document produced by a reader is FlowGraph's canonical editable mesh
model. The 3D view is a derived visualization of that document, not a separate
editable source.

## Build and run a workflow in the application

1. Add nodes from the **Nodes** menu or the node search dialog.
2. Connect an output port to a compatible input port in the **Workflow** panel.
   Ports are typed, so FlowGraph rejects incompatible connections unless an
   explicitly registered automatic conversion is available. Initially, FlowGraph
   converts `Integer` to `Float` and `Float` to `Text`. Converted connections are
   amber; select one to see the conversion in the **Node Inspector**. See
   [Edge Conversions](../reference/edge-conversions.md) for the complete behavior.
3. Expand a node and configure its parameters. A parameter that is connected to
   another node uses the incoming value for that execution.
4. Select **Edit → Auto Organize Nodes** to arrange the active
   workflow from left to right according to its dependencies. Nodes in the same
   dependency layer are ordered to reduce crossing connections and evenly
   distributed on a regular grid. The action can be undone.
5. Click **Run work** in the workflow toolbar below the application menus. Nodes execute in stable
   topological order. Use **Immediate execution** to automatically execute the
   selected node and its executable downstream nodes after changing one of its
   parameters.
6. Select a node or edge to inspect its inputs, outputs, and execution state in
   the **Node Inspector**.

Use the orange nodes in the **Workflow** menu to define a reusable workflow
interface. Give each **Workflow Input** and **Workflow Output** a unique name,
then connect the input node's output to the graph and connect graph values to the
output nodes. Those names become the inputs and outputs used by saved workflows,
Python callers, and **Run Full Workflow**.

Use **Run → Run Only Selected** when only one node needs to be executed. If a node
fails, successful validated results from upstream nodes remain available for
inspection. Independent branches can continue, while nodes that depend on a
failed result remain unexecuted.

## Run workflows from the command line

Inspect the public interface, then provide the inputs you want to change:

```bash
flowgraph inspect workflow.json
flowgraph run workflow.json --input message=hello
```

`-i` is an alias for `--input`; repeat either option for multiple inputs.
Values are decoded as JSON when possible, so `count=0` and `enabled=false`
provide an integer and a boolean, while `message=hello` provides text.

### Omitted inputs and saved parameter values

`flowgraph inspect workflow.json` shows each published input's resolved default
on the right of its input line, for example:

```text
Inputs:
  message: Text (input.value)  default: 'saved message'
```

Inputs without a usable default show `default: (none; required)`. Conflicting
downstream defaults show `default: (conflicting saved values; provide --input)`;
inspection still displays the rest of the workflow. Defaults use the same lookup
as `flowgraph run`, including nested workflows and directly exported parameters.
Inspection does not execute nodes or emit omitted-input execution warnings.

You can omit an input when the workflow contains a usable saved parameter value
for it:

```bash
flowgraph run workflow.json
```

For example, if a **Workflow Input** named `message` connects to `target.value`
and that node has the saved parameter `value: "saved message"`, FlowGraph uses
`"saved message"` for the omitted input. It prints this warning to **stderr**:

```text
flowgraph: Warning: Workflow input 'message' was not provided; using saved parameter value 'saved message' from target.value.
```

The lookup follows Workflow Input connections and published inputs inside nested
workflows. It also supports parameters exported directly as workflow inputs.
It reads parameter values without executing nodes to discover defaults. Values
such as `0`, `false`, and an empty string count as provided defaults.

The precedence is:

1. An explicit `--input NAME=VALUE` always wins; no fallback warning is issued
   for that input.
2. Node parameter `--override NODE-ID.PARAMETER=VALUE` assignments are applied
   before omitted-input resolution, so they can change the fallback value.
3. Otherwise, an omitted input uses a compatible saved parameter value from its
   downstream target or directly exported parameter.

If multiple downstream parameters supply saved values, they must agree after
type normalization. Conflicting values produce an error asking for an explicit
`--input`. If no usable saved value exists, the command reports
`Missing required workflow inputs`. Ordinary data ports do not acquire a default
merely because they are connected to a Workflow Input node.

Fallback values must satisfy the published input type, with registered value
conversions applied where available. FilePath values retain their dependent
files; float 3D vectors accept saved numeric components and normalize them to
floats.

Warnings identify the input, chosen value, and source parameter address. Nested
addresses include their parent node, for example `nested/target.value`. Public
outputs stay on stdout, or go to the file selected with `--json-output`:

```bash
flowgraph run workflow.json --json-output results.json 2> warnings.log
```

Input fallbacks and overrides affect only this execution; they do not rewrite
the workflow JSON. This fallback behavior belongs to `flowgraph run` and
`execute_cli_workflow()`; it does not change the input requirements of
`WorkflowGraph.execute()` or other execution APIs.

## Save and load workflows

Use **File → Save workflow** to write the graph to JSON and **File → Load
workflow** to reopen it. A saved workflow contains:

- the `flowgraph-workflow` format ID and version;
- node IDs, definitions, parameters, and canvas positions; and
- port-addressed connections between nodes.

The JSON is intended to be human-readable and portable. Paths are stored exactly
as entered. At runtime, `~` expands to the user's home directory, and relative
paths resolve from the Python process's current working directory—not from the
directory containing the workflow JSON file. Use absolute paths or configure
paths with runtime overrides when running the same workflow on another machine.

## Execute a workflow from a Python script

The UI is optional: saved workflows can be executed headlessly from a script.
Install FlowGraph in the environment where the script runs, then call
`execute_workflow_file()`. The `parameter_overrides` mapping is keyed by node
instance ID, so it changes inputs for this run without modifying the JSON file.

This example uses the packaged `SimpleReadMesh.json` demo workflow. Replace
`workflow_path` and `mesh_path` with paths to your own workflow and mesh:

```python
from pathlib import Path

from flowgraph.application.workflow_io import execute_workflow_file


workflow_path = Path("src/flowgraph/testdata/SimpleReadMesh.json")
mesh_path = Path("data/input.stl").resolve()

result = execute_workflow_file(
    workflow_path,
    parameter_overrides={
        "file-path": {"path": str(mesh_path)},
    },
)

print("Executed nodes:", result.execution_order)

# Outputs are addressed by node ID and output-port name.
mesh_document = result.node_outputs["load-muscat"]["mesh"]
print("Loaded:", type(mesh_document).__name__)

# A sink has no output, so inspect the value delivered to its input instead.
mesh_for_view = result.node_inputs["mesh-sink_2"]["mesh"]
assert mesh_for_view is mesh_document
```

### Workflow inputs and outputs

A Python-built workflow can publish a node input (including a parameter port) as a
workflow input, and publish node outputs as workflow outputs. Exported inputs must
remain unconnected inside the graph; callers provide their values when executing the
workflow. The workflow then behaves like a node:

```python
workflow.add_input("text", "transform", "value", registry)
workflow.add_output("result", "transform", "result", registry)

outputs = workflow.execute({"text": "hello"}, registry)
# The same interface is available as workflow.executor(registry).
```

The public interface is included when the workflow is saved, so it survives a JSON
round trip.

A workflow can also be executed inside another workflow with **Run Full Workflow**.
Expand the node and click **Edit workflow** to replace the current Workflow view with
the nested graph. Build the nested graph normally, using **Workflow Input** and
**Workflow Output** nodes to define its public interface. Click **Quit workflow** at
the top of the Workflow view to return to the parent graph.

The node exposes typed dynamic ports matching the nested workflow's published inputs
and outputs: connect values to the published input names and use published output
names downstream. It also emits the nested `WorkflowRunResult`, including execution
order and per-node inputs and outputs, on `result`. Leaving a nested editor refreshes
its parent node's ports and invalidates that node and all downstream parent nodes.

Published interface types are inferred automatically. A **Workflow Output** exports
the type of its connected upstream value. A **Workflow Input** exports a type that can
safely feed every connected internal destination, including registered conversions.
If the boundary is unconnected or its destinations have no common safe type, it remains
**Any**. This lets parent workflows reject incompatible connections while retaining a
flexible interface when the internal graph does not determine one type.

`execute_workflow_file()` returns a `WorkflowRunResult`. Its
`node_outputs` and `node_inputs` mappings retain the values produced and
consumed by each node. Runtime overrides are not written back to the workflow
file. To use a custom node catalog, create a `NodeRegistry` and pass it through
the keyword-only `registry` argument.
See [Create and Run Python Nodes](custom-nodes.md) for a runnable example of
defining a node, registering it alongside the built-ins, and wiring it into a
Python workflow.

For a workflow that is already built in Python, use `execute_workflow(workflow,
registry)` instead. The [Workflow Nodes](../reference/nodes.md) reference
explains definitions, ports, parameters, validation, and output contracts.