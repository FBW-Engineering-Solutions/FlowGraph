---
id: user-guide.custom-nodes
title: Create and Run Python Nodes
section: User Guide
order: 26
description: Define a typed node, register it, wire it into a Python workflow, and execute it.
---

# Create and run Python nodes

Use a **User Function** node for a short function entered in an editor (see
[Code nodes](../reference/adapters/code.md)). To reuse a Python implementation
across scripts, define a `NodeDefinition` and register it with a `NodeRegistry`.
The built-in [adapter catalog](../reference/adapters/index.md) lists the nodes
already supplied by FlowGraph; you do not need to redefine those nodes.

## Complete example

Run this script with `python example.py` in an environment with `flowgraph`
installed (or `uv run python example.py` from this repository). It creates a
custom **Scale Integer** node, connects the built-in **Integer Input** to it,
executes the graph, and saves and reloads it:

```python
from collections.abc import Mapping
from typing import Any

from flowgraph.adapters.data_types import INTEGER, ParameterKind
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import (
    ExecContext,
    NodeDefinition,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
    WorkflowEdge,
    WorkflowExecutor,
    WorkflowGraph,
)
from flowgraph.application.workflow_io import execute_workflow_file, save_workflow


def scale_integer(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _context: ExecContext,
) -> Mapping[str, Any]:
    return {"result": inputs["value"] * parameters["factor"]}


SCALE_INTEGER = NodeDefinition(
    id="scale-integer",
    label="Scale Integer",
    description="Multiply an integer by a configurable factor.",
    icon="mdi-multiplication",
    requirements=(),
    ports=(
        PortDefinition("value", PortDirection.INPUT, INTEGER, "Value"),
        PortDefinition("result", PortDirection.OUTPUT, INTEGER, "Result"),
    ),
    parameters=(ParameterDefinition("factor", ParameterKind.INTEGER, "Factor", 2),),
    executor=scale_integer,
)

registry = create_node_registry()  # Includes the built-in set-int node.
registry.register(SCALE_INTEGER)

graph = WorkflowGraph()
graph.add_node(registry.create_instance("set-int", "source", parameters={"value": 7}))
graph.add_node(registry.create_instance("scale-integer", "scale", parameters={"factor": 3}))
graph.add_edge(WorkflowEdge("source", "value", "scale", "value"), registry)

assert not graph.validate(registry)
result = WorkflowExecutor(registry).run(graph)
assert result.node_outputs["scale"]["result"] == 21
print(result.node_outputs["scale"]["result"])

save_workflow(graph, "scaled-workflow.json")
# Register the custom definition again before loading in a different process.
reloaded = execute_workflow_file("scaled-workflow.json", registry=registry)
assert reloaded.node_outputs["scale"]["result"] == 21
```

`scale-integer` is the reusable **definition ID**; `scale` is this graph's unique
**instance ID**. Edges use instance IDs and the exact port names, not display
labels. `factor` is automatically an optional input port as well as a parameter:
if connected, its incoming value overrides the configured value for that run.
Set `port=False` on a `ParameterDefinition` to keep a setting local to the node.
Required inputs must be connected (or supplied through the workflow interface).

The executor receives named inputs, instance parameters, and an `ExecContext`.
The context contains `parallel_tasks`, `gpu_available`, and
`connected_output_ports`. Return a mapping keyed by declared output names with
values matching their `DataType`; return `{}` for a node without outputs.
FlowGraph validates edges and outputs and reports node execution failures with
the instance and definition IDs. The example's `requirements=()` means no
*additional* direct execution dependency beyond FlowGraph. If your executor
needs another distribution, declare it with `requirements=("py:package-name",)`;
this is metadata, not an installer. Consult [Workflow nodes](../reference/nodes.md)
for port types, parameter behavior, and requirements conventions.

## Reuse, publish, and load

Saved workflow JSON records the definition ID, **not** its Python executor.
When loading or executing that file later, import the module defining your node
and register the definition in the registry passed to `load_workflow()` or
`execute_workflow_file()`. `create_node_registry()` contains the built-in nodes;
register your own definition on that registry to use both. For a custom-only
registry, construct `NodeRegistry()` and register every definition used by the
graph. `registry.register()` rejects duplicate IDs.

To expose a graph value to a Python caller, call
`graph.add_output("scaled", "scale", "result", registry)` and then use
`graph.execute({}, registry)["scaled"]` (or access the per-instance value from
`WorkflowExecutor.run(graph).node_outputs`). To accept a value supplied by the
caller rather than the built-in source, omit the source and edge and call
`graph.add_input("number", "scale", "value", registry)`; then execute with
`graph.execute({"number": 7}, registry)`. Exported inputs must not also be
connected to another node inside the graph. See the [Workflows guide](workflows.md)
for running saved workflows and exporting graph interfaces.

## Load Python-file plugins from the CLI or server

Put reusable definitions and their executors in a Python file, then export them
in `AVAILABLE_NODES`. The file must not run a workflow at import time. For example,
save this as `custom_nodes.py`:

```python
from flowgraph.adapters.data_types import INTEGER, ParameterKind
from flowgraph.application.workflow_core import (
    NodeDefinition,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
)


def scale_integer(inputs, parameters, context):
    return {"result": inputs["value"] * parameters["factor"]}


SCALE_INTEGER = NodeDefinition(
    id="scale-integer",
    label="Scale Integer",
    icon="mdi-multiplication",
    ports=(
        PortDefinition("value", PortDirection.INPUT, INTEGER),
        PortDefinition("result", PortDirection.OUTPUT, INTEGER),
    ),
    parameters=(ParameterDefinition("factor", ParameterKind.INTEGER, "Factor", 2),),
    executor=scale_integer,
)

AVAILABLE_NODES = (SCALE_INTEGER,)
```

Load these definitions before reading a saved workflow that uses `scale-integer`:

```bash
uv run flowgraph inspect /path/scaled-workflow.json --plugin /path/custom_nodes.py --full
uv run flowgraph run /path/scaled-workflow.json --plugin /path/custom_nodes.py \
  --override scale.factor=3
uv run flowgraph serve --workspace /path/workspace --plugin /path/custom_nodes.py
```

Repeat `--plugin` for multiple files. Built-ins are registered first, followed by
plugins in option order; duplicate definition IDs and repeated file paths are
errors. Each file must export an iterable containing only `NodeDefinition`
objects. Definitions are not discovered from arbitrary module globals.

Relative plugin paths resolve from the command's working directory, **not** the
workflow location or server workspace; `~` is expanded. Plugin directories are
not added to `sys.path`: install helper modules and dependencies in the same
Python environment. Plain files are supported, not package-relative imports.
Each successfully imported file is reused within its process. Restart the CLI
invocation or server after changing plugin code; hot reload is not supported.

The server validates plugins at startup, includes their metadata in
`GET /api/v1/catalog` under `Plugins / <filename>`, and loads the same configured
files in both stateless and incremental execution workers. Keep those files
unchanged while the server runs. Workers execute with the workspace as their
working directory; use `__file__` for resources relative to the plugin itself.
An editor must use the server's catalog, or import a matching custom catalog,
to author these nodes. This does not install custom code into browser WASM or
the Desktop application's built-in-only registry.

Python hosts can use the same loader without the CLI:

```python
registry = create_node_registry(plugins=["/path/custom_nodes.py"])
reloaded = execute_workflow_file("scaled-workflow.json", registry=registry)
```

`inspect_workflow(..., plugins=[...])` and `execute_cli_workflow(..., plugins=[...])`
also accept explicit files. Native JSON hosts can pass a configured registry to
`execute_workflow_json(document, registry=registry)`; HTTP clients cannot select
or load plugin files through execution options.

**Trust boundary:** imports execute arbitrary Python in the CLI/server process
and workers with your OS permissions, even during inspection. Only load files
you trust. Plugins are not sandboxed, installed automatically, embedded in
workflow JSON, or loaded from paths named by a workflow or HTTP request. JSON
continues to store definition IDs and parameters; supply the files again when
running in another process. Ordinary built-in-only invocations are unaffected.

## Workspace Muscat solver

The source checkout includes `workspace/MuscatSolver.py`, exporting
`muscat-initial-strain-solver` (**Muscat Initial Strain Solver**). Load the trusted
file using `--plugin` with `serve`, `run`, or `inspect`. It is not built in,
automatically discovered by Desktop, or installed in browser WASM.

Connect a mesh reader to `mesh` and the solved `mesh` output to a viewer or
**Write Mesh** for VTK export. Outputs contain nodal `Displacement`, initial
strain components, and element-center `sigma_*` fields. The input is unchanged;
unchanged storage is shared read-only.

- `axisymmetric=true` requires a 2D `(r,z)` mesh with strictly positive radius;
  `false` requires 3D. Axis-touching meshes are not supported.
- Set `young` and `poisson` in consistent units. Defaults (1.0, 0.3) are
  illustrative, not calibrated material properties.
- `strain_strategy`: `analytical` uses the supplied height profile;
  `from_WK1_points` / `from_WK1_cells_center` read `strain_field` (default `strain`).
  Imported tensors must be finite row-major `(N,9)` or `(N,3,3)`, over all nodes
  or elements (including boundary elements). Only diagonal entries are retained.
  Axisymmetry maps xx to rr, yy to zz, zz to tt.
- Default supports use the example's geometry-specific zones. Optional
  `boundary_A/B/C` selectors replace them. Axisymmetric A fixes axial motion
  near `(20,0.5)`; `bridage=hyperstatique` adds B near `(10,0.5)`. In 3D A/B
  must select linear surface elements and block their local normal, while C
  fixes global displacement component 1. Empty selections fail explicitly.
- Stress order: rr,zz,tt,rz (axisymmetric), xx,yy,zz,yz,xz,xy (3D).
  Lower-dimensional boundary cells receive zero stress. The formulation uses
  P1 displacement and initial-strain loading with no external forces.

The plugin includes installed-Muscat compatibility forms and P1 constraints;
reciprocal radius is evaluated at quadrature points to avoid unsupported native
negative powers. See the file's module documentation for the complete contract.

## Export extra nodes for the Web Editor

The Web Editor reads catalog JSON for its menu, ports, and parameter editors.
A Python `NodeRegistry.register()` call alone does not update the Web Editor.
To export your own definitions **alongside the built-in nodes**, add this after
the `SCALE_INTEGER` definition in the example above (or import it from your
custom module):

```python
from flowgraph.adapters import AdapterGroup
from flowgraph.application.workflow_web_catalog import write_workflow_web_catalog

write_workflow_web_catalog(
    "node-catalog.json",
    extra_groups=(AdapterGroup("My Nodes", (SCALE_INTEGER,)),),
)
```

Run the script with `python example.py` (or `uv run python example.py` from the
core checkout). The output path's parent directory must already exist. To
export several nodes, pass them in the group's tuple; to create multiple menu
groups, pass several `AdapterGroup` objects. Node definition IDs must be unique
across both built-in and extra groups; duplicates raise `ValueError`. The
exporter includes each node's static ports, parameters, icon, requirements, and
other metadata but **not** its Python executor. Dynamic ports may need editor
support beyond this static metadata.

Open the Web Editor website and select **Load custom catalog** in the **Nodes**
sidebar. Choose the generated `node-catalog.json`; your **My Nodes** group will
appear alongside the built-in groups. You do not need to clone or build the Web
Editor. The imported catalog is used only for the current page session: reload
the page to restore the bundled catalog, or select **Use bundled catalog**. The
editor will not switch catalogs if the current workflow (including a nested
workflow) contains nodes absent from the catalog you are switching to.

Importing a catalog enables authoring and displaying custom nodes, **not browser
execution**: the current WASM worker creates a built-in-only registry. Browser
execution requires bundling the custom Python implementation into the browser
runtime and registering it there. For local Python execution of a workflow
exported from the website, supply `--plugin` to `flowgraph run` or `flowgraph serve`,
or register the custom definition before loading the workflow as shown above.
Treat third-party workflow files and user code as
trusted executable content; the workflow format is not a sandbox.

If contributing a node to the built-in catalog instead, add its definition to
an `AdapterGroup` in `src/flowgraph/adapters/__init__.py`, document its ID and
behavior on the corresponding [adapter page](../reference/adapters/index.md),
and add tests.
