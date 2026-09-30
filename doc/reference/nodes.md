---
id: reference.nodes
title: Workflow Nodes
section: Reference
order: 10
description: Understand node definitions, ports, parameters, and outputs.
---

# Workflow nodes

A **node** is one step in a FlowGraph workflow. It describes an operation that can
receive typed values, use configured settings, and produce typed values for the
next node. Nodes are connected to form a directed workflow graph. Nodes are
provided by adapters, so the same workflow model can support finite-element
meshes, Pillow images, and additional domains without changing the graph engine.

For example, a workflow can use a **Select file** node to produce a file path and
pass that path to **Read Mesh (Muscat)**. The reader then produces a mesh document
that can be consumed by later processing or visualization nodes:

```text
Select file ── path (Text) ──▶ Read Mesh (Muscat) ── mesh (Mesh document) ──▶ …
```

## Node definition and node instance

FlowGraph separates the reusable description of a node from the node placed in a
workflow:

- A **node definition** is the catalog entry. It supplies the node's name,
  description, icon, executor, ports, parameter schema, default values, and
  direct execution requirements.
- A **node instance** is one occurrence of that definition in a workflow. It has
  its own instance ID, canvas position, and configured parameter values. Two
  instances of the same definition can therefore use different files or values.

The definition determines what a node *can* accept and produce. The instance
determines how that particular node is configured and where it appears on the
canvas.

### Execution requirements

Every node definition has a `requirements` tuple, exported as a list in the web
catalog. Entries use `py:<package>` for an installable Python distribution
(for example `py:pillow`, whose import name is `PIL`), `native:<command>` for
a required command-line executable, or `os:<platform>` for a platform restriction
(for example `os:win` or `os:web`). An empty list means the node has no *additional*
direct execution requirements beyond FlowGraph's runtime; it does not mean that
FlowGraph itself has no dependencies. Requirements are descriptive metadata, not
an automatic installation or execution check. They do not list transitive packages.

The static list cannot describe dependencies selected by a parameter or supplied
by user code: for example, the `remesh` node may need an MMG backend when that
backend is selected, and `user-function` may import arbitrary Python packages.
Composite workflow nodes inherit the requirements of their child nodes at run
time. `download-url` runs on both desktop Python and supported Pyodide setups, so
it has no single OS restriction.

## Ports

Ports are named, typed connection points on a node. A connection always runs from
an output port on one node to an input port on another node.

### Input ports

Input ports receive values from upstream nodes. An input may be required or
optional:

- A **required** input must be connected before a complete workflow can execute.
- An **optional** input may be left unconnected; the node can use its parameter,
  an internal default, or another fallback defined by the operation.

Connections use the port's stable name, not only its display label. FlowGraph checks
the data type before accepting a connection. For example, a `Text` output can be
connected to a `Text` input, while a mesh document cannot be connected directly to
an integer input. FlowGraph also permits explicitly registered directed automatic
conversions: `Integer` to `Float`, and `Float` to `Text`. Converted connections are
shown in amber and identify their conversion in the Node Inspector. Other type
differences require an explicit conversion node. See [Edge Conversions](edge-conversions.md)
for the complete rule list and runtime behavior.

### Output ports

Output ports expose values produced after the node executes. Each output has a
name and data type, and downstream connections select the specific output by
name. A node may have more than one output; every declared output must be
returned by the node operation with the declared type.

Outputs are retained in the workflow run result. This makes intermediate values
available to downstream nodes and to the node inspector after execution.

### Port labels and types

The label shown in the editor is for readability; the type is the compatibility
contract. Common FlowGraph types include:

| Type | Meaning |
| --- | --- |
| `Text` | A Python string, such as a file path or field name |
| `Integer` | A whole-number value |
| `Float` | A floating-point value |
| `3D Vector` | A three-component numeric vector |
| `Mesh document` | FlowGraph's canonical editable Muscat mesh document |
| `Table` | Tabular data represented by a mapping |

## Parameters

Parameters are values configured on an individual node instance. They are used
when the node executes and can be edited in the node UI. A parameter definition
specifies its name, data kind, display label, default value, placeholder, and,
where applicable, selectable options or file patterns.

Many parameters are also exposed as optional input ports. This allows a value to
come either from the node's editor or from another node:

```text
local parameter value  ── used when the parameter port is unconnected
upstream output       ── used when the parameter port is connected
```

When a parameter port is connected, the incoming value is authoritative for that
execution. The editor disables local editing for that parameter, and execution
stores the resolved value on the node instance so the configured workflow reflects
what was used.

Not every parameter must be a port. UI-only or selection parameters can remain
local to the node. For example, an uploaded server filename can be selected in the
node editor without becoming a connectable workflow input.

## Execution and outputs

## Adapter catalog

The built-in nodes are grouped in the editor by adapter family. The complete
reference for each group is split into the following pages:

| Editor group | Reference |
| --- | --- |
| Inputs | [Input nodes](adapters/inputs.md) |
| Files | [File nodes](adapters/file.md) |
| Readers | [Reader nodes](adapters/readers.md) |
| Mesh Gens | [Mesh-generation nodes](adapters/mesh-gens.md) |
| Mesh Creation | [Mesh-creation nodes](adapters/mesh-creation-tools.md) |
| Filters | [Filter nodes](adapters/filters.md) |
| Mesh Ops | [Mesh-operation nodes](adapters/mesh-ops.md) |
| Field Ops | [Field-operation nodes](adapters/field-ops.md) |
| File Conversion | [File-conversion nodes](adapters/file-conversion.md) |
| Writers | [Writer nodes](adapters/writers.md) |
| Sinks | [Sink nodes](adapters/sinks.md) |
| Doc | [Documentation nodes](adapters/doc.md) |
| GUI | [GUI nodes](adapters/gui.md) |
| Image Tools | [Image tool nodes](adapters/image-tools.md) |
| Table Tools | [Table tool nodes](adapters/table-tools.md) |
| Code | [Code nodes](adapters/code.md) |
| Workflow | [Workflow nodes](adapters/workflow.md) |
| External Tools → CoSApp | [CoSApp nodes](adapters/cosapp.md) |
| External Tools → Plaid | [Plaid nodes](adapters/plaid.md) |

## GUI slider nodes

The **Nodes → GUI** submenu contains **Float Slider** and **Integer Slider**.
Configure the current value in the node editor; the current value is displayed as a
slider and is emitted from the typed `value` output. The `min` and `max` parameters
are exported input ports, so other nodes can provide dynamic slider bounds.

The float slider emits a `Float` and the integer slider emits an `Integer`. Slider
values must remain within the configured inclusive minimum and maximum.

When a workflow runs, FlowGraph:

1. Validates node definitions, connections, port names, types, required inputs,
   and graph cycles.
2. Resolves incoming connections into named input values.
3. Executes nodes in a stable topological order.
4. Passes each node's outputs to connected downstream inputs.
5. Validates that the returned output names and values match the node definition.
6. Retains named inputs and outputs for inspection and later workflow steps.

An executor returns a mapping such as `{"mesh": mesh_document}` or
`{"path": "/data/model.xdmf"}`. The mapping keys must match the node's declared
output port names exactly. If an operation fails or returns an undeclared type,
FlowGraph reports the node and definition involved in the error.

## User Function node

The **User Function** node (`user-function`) lets a workflow run trusted local
Python code entered directly in the node editor. Define one regular function,
for example:

```python
def Execute(name: str, scale: float) -> tuple[str, float]:
    return (name.upper(), scale * 2)
```

Each positional parameter becomes an optional input port and receives `None` when
it is not connected. No annotation (or `Any`) creates an `Any` port; `str`,
`bool`, `int`, `float`, `list[str]`, `list[int]`, and `list[float]` create the
matching typed ports. The fixed-length `tuple[...]` return annotation determines
the output count and types: the example creates `output1: Text` and
`output2: Float`. Use `tuple[()]` for no outputs. The returned tuple must match
the declared length and types.

Editing the code invalidates the node and every downstream node, removing their
cached values until they are executed again. The editor provides Python syntax
highlighting and indentation assistance through locally bundled CodeMirror.
Code is executed as Python in the local application process, so this node must
only be used with trusted code.

## Example: file path to mesh

The initial workflow demonstrates the complete data flow:

1. **Select file** has a `File path` parameter and a `path` output of type `Text`.
   It produces the selected path without reading the file.
2. **Read Mesh (Muscat)** has a required `path` input of type `Text` and a `mesh`
   output of type `Mesh document`.
3. The `path` output is connected to the reader's `path` input.
4. After execution, the reader's `mesh` output is available to downstream mesh
   operations and the 3D workspace.

For the editor layout and connection interactions, see the [Interface guide](../user-guide/interface.md).