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
exported from the website, register the custom definition before loading the
workflow as shown above. Treat third-party workflow files and user code as
trusted executable content; the workflow format is not a sandbox.

If contributing a node to the built-in catalog instead, add its definition to
an `AdapterGroup` in `src/flowgraph/adapters/__init__.py`, document its ID and
behavior on the corresponding [adapter page](../reference/adapters/index.md),
and add tests.
