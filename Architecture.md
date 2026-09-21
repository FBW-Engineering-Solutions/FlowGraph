# FlowGraph Core Architecture

## Purpose

FlowGraph Core is a GUI-free Python workflow engine. It lets applications and
command-line users compose, validate, execute, persist, and inspect typed
workflows. The core owns workflow semantics; presentation clients, if any, are
external consumers and are not required to install or use this package.

The package supports reusable adapters for mesh, image, file, documentation,
and utility operations. Mesh processing is an important use case, but the graph
model is domain independent.

## Package boundaries

The source package is organized under `src/flowgraph/`:

- `application/` owns workflow definitions, validation, execution, persistence,
  history, layout, command-line services, catalog export, and WASM execution.
- `adapters/` provides node definitions and integrations for supported data
  domains and external libraries.
- `domain/` owns domain state, including the mesh document model.
- `resources.py` resolves package data independently of the current working
  directory.
- `core_cli.py` exposes the headless `flowgraph` command.

Core modules must not depend on GUI frameworks, browser shells, or external
presentation packages. This keeps imports and command-line execution suitable
for local automation and server-side use.

## Workflow model

`WorkflowGraph` contains `NodeInstance` objects and named `WorkflowEdge` values.
A `NodeDefinition` describes ports, parameters, defaults, and execution behavior.
`NodeRegistry` provides the available definitions.

Validation rejects invalid endpoints, competing input connections, incompatible
port types, and cycles. Registered directed port conversions are applied during
execution. Execution is stable and topological. `WorkflowRunResult` retains
resolved inputs and outputs; `NodeExecutionError` can expose partial results for
completed independent work.

Composite nodes contain nested workflows. Boundary nodes map named child inputs
and outputs to the parent workflow.

## Persistence

Workflows are UTF-8 JSON documents with format identifier
`flowgraph-workflow`. They store node parameters, positions, named-port edges,
and nested workflows.

External paths remain user-provided values. At runtime, `~` expands and relative
paths resolve from the executing process working directory. Packaged test-data
paths can be represented with the portable `{testdata}` token.

## Data and adapter boundaries

For mesh workflows, Muscat mesh data is authoritative. VTK is an adapter
representation used by operations that need it; it is not the editable source of
truth. Image operations use Pillow-backed adapter types.

Adapters define their public ports and parameters through the workflow model.
They should keep external-library details at the adapter boundary and avoid
changing core graph semantics for domain-specific behavior.

## Command-line interface

The `flowgraph` command is headless. It supports workflow inspection and
execution without requiring a graphical environment:

```bash
flowgraph inspect workflow.json
flowgraph run workflow.json --input name=value
flowgraph run workflow.json --override node-id.parameter=value
flowgraph run workflow.json --json-output results.json
```

## External-client interfaces

FlowGraph can export a deterministic, non-executable node catalog with
`python -m flowgraph.application.workflow_web_catalog`. The catalog includes
static authoring metadata but intentionally excludes executors, runtime Python
types, and callable behavior.

The WASM execution boundary provides a restricted node registry for compatible
browser runtimes. It deliberately excludes capabilities that are not available
or appropriate in that environment, such as local file readers and writers,
external tools, and unsupported dependencies.

## Distribution and quality

The project uses a `src/` layout, setuptools, `uv`, pytest, and Ruff. It builds a
source distribution and a platform-independent pure-Python wheel. Runtime
libraries may have their own platform-specific installation requirements, but
FlowGraph does not build native extensions.

Changes to core behavior must update tests, NumPy-style docstrings, relevant
user documentation, and workflow-format compatibility notes. The CI quality gate
runs formatting/linting and tests from the locked development environment.

## Security boundaries

Workflow JSON is untrusted input and is parsed with strict structural and type
validation before execution. Persistence does not deserialize arbitrary Python
objects. File readers and writers operate on paths supplied by the caller, and
the remote-download adapter performs network access only when explicitly used
by a workflow. The user-function adapter intentionally executes Python supplied
by the workflow author and is therefore a trusted-code capability, not a
sandbox; callers must not execute untrusted workflows with that node enabled.

Adapters that invoke external tools, read local files, download URLs, or execute
user code must be treated as process capabilities. Applications embedding the
core should apply their own filesystem, network, CPU, memory, timeout, and
process-isolation controls when workflows are supplied by another party.
