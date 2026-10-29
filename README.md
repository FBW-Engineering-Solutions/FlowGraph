# FlowGraph Core

`FlowGraph` is the GUI-free Python workflow engine. It provides typed workflow
composition, validation, persistence, execution, adapters, mesh and image data
operations, browser-WASM execution support, and metadata-only catalog export
for compatible external clients.

> **Alpha status:** FlowGraph Core `0.1.x` is an alpha series for evaluation,
> development, experimentation, and early adopter feedback. APIs and workflow
> behavior may change before `1.0.0`. See [`Release Policy`](docs/policies/release-policy.md).

## Incremental workflow execution

`WorkflowExecutor` remains stateless. Use `WorkflowSession` for selected targets,
dependency-aware cache reuse, forced runs and session lifecycle. See
[`Incremental execution`](doc/reference/incremental-execution.md) for the Python
API, node safety contracts, transport options and resource limits.

## Development setup

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

See [`Contributing`](.github/CONTRIBUTING.md) for prerequisites, development
workflow, testing, documentation, and pull-request expectations.

## Headless workflows

The `flowgraph` command is headless and has no GUI runtime dependency:

```bash
uv run flowgraph inspect workflow.json
uv run flowgraph inspect workflow.json --full
uv run flowgraph inspect workflow.json -i name=value --override node-id.parameter=value
uv run flowgraph run workflow.json --input name=value
uv run flowgraph run workflow.json -i name=value
uv run flowgraph run workflow.json --override node-id.parameter=value
uv run flowgraph run workflow.json --json-output results.json
```

Use `--input` or its short form `-i` for each published workflow input; repeat
the option to provide multiple inputs.
`flowgraph inspect` displays the resolved default to the right of each published
input, or marks it as required or having conflicting saved values.
Inspection is compact by default; add `--full` (or `-f`) to include the workflow
graph. Arbitrary-code warnings remain visible in both modes.
Inspection accepts the same `--input` / `-i` and `--override` assignments as
execution: overrides update the displayed defaults, and explicit inputs take
precedence and are marked `(--input)`. It never executes nodes or saves changes.
When an input is omitted, `flowgraph run` uses its downstream node's saved
parameter value and prints a warning to stderr identifying the input, value,
and parameter. This also works for directly exported parameters and nested
workflow inputs. Explicit inputs take precedence; parameter overrides are applied
before resolving defaults. Inputs without usable saved values remain required,
and conflicting saved values require an explicit `--input`.
For examples and warning output, see
[Omitted inputs and saved parameter values](doc/user-guide/workflows.md#omitted-inputs-and-saved-parameter-values).

Workflows use the versioned `flowgraph-workflow` JSON format. Core validation and
execution are UI-independent.

### JSON execution boundary

Python clients and browser-hosted Python workers use the same entry point:

```python
from flowgraph.application.workflow_execution import execute_workflow_json

result_json = execute_workflow_json(workflow_json)
```

The response includes execution order, public outputs, retained node values,
display previews, warnings, and structured errors. A process-local node registry
is reused, but each call reconstructs its workflow. This API does not provide a
server, authentication, cancellation, or filesystem isolation.

Mesh display previews retain scalar values or vector magnitudes in `fields` and
`cell_fields`. Multi-component fields additionally expose their original tuples
in `field_components` and `cell_field_components`, indexed by vertex or surface
triangle respectively, so viewers can select an individual component without
rerunning the workflow. These preview projections do not modify the input mesh.

The former WASM-specific execution module has been removed without a compatibility
alias. Browser clients must update their import and rebuild/stage their core wheel
together; the workflow file and execution response formats are unchanged.

## Experimental local server

The prototype branch includes an authenticated, loopback-only execution API:

```bash
uv run flowgraph serve --workspace /absolute/path/to/existing/workspace
```

Port 8765 and the allowed editor origin `https://flowgraph-web.fbw-es.com` are
defaults; explicit `--allow-origin` values replace that origin. The editor still
requires bearer authentication and browser local-network permission. Click the
printed **Open editor** link to pass the token and port automatically; keep the
link private.

It runs one workflow at a time in a cancellable native subprocess and provides
runtime metadata, catalog, and workspace file endpoints. Core is API-only and never
serves editor assets. Web and desktop clients own their GUI hosting and explicitly
allow their origin with `--allow-origin`. Native workflow code is **not sandboxed**.
See [Local server API and limitations](docs/local-server.md) for authentication,
request/response formats, examples, limits, and shutdown behavior.

## Package artifacts

Build the portable, pure-Python source distribution and wheel with:

```bash
uv build --out-dir dist/
```

The resulting wheel is compatible with all supported Python platforms. See
`packaging/README.md` for release details.

The repository also includes a Conda recipe under `packaging/conda/`. FlowGraph
is distributed through the [`flowgraph` Anaconda channel](https://anaconda.org/channels/flowgraph):

```bash
conda install -c flowgraph flowgraph
```

Docker, operating-system package managers, and third-party mirrors are not
supported release channels at this time. See
[`Release Channels`](docs/policies/release-channels.md) for the release policy.

FlowGraph Core declares Python 3.11 or newer. CI covers Python 3.11, 3.12, 3.13, and 3.14 on
GitHub-hosted Ubuntu, Windows, and macOS runners; a platform/version combination
is supported only after its release-candidate job passes. See
[`Support Policy`](docs/policies/support-policy.md) for compatibility, deprecation,
maintenance, and unsupported-use policies.

## Catalog export

FlowGraph can export non-executable node metadata for tools that need to author
or structurally validate workflow JSON:

```bash
uv run python -m flowgraph.application.workflow_web_catalog node-catalog.json
```

The catalog intentionally excludes node executors and other callable runtime
behavior.

## Documentation and support

- [FlowGraph documentation](https://flowgraph.readthedocs.io/en/latest/)
- [Built-in node catalog](doc/reference/adapters/index.md) and
  [Python custom-node guide](doc/user-guide/custom-nodes.md).
- The website documentation lives in `doc/` (outside the Python package).
  To build the Read the Docs site locally, run
  `uv run --with zensical zensical build -f zensical.toml` from this repository.
- [`Architecture`](docs/architecture.md) describes the core boundaries and workflow
  model.
- [`Support Policy`](docs/policies/support-policy.md) describes supported environments and
  compatibility expectations.
- [`SECURITY.md`](SECURITY.md) explains private vulnerability reporting and the
  security boundaries of workflows and adapters.
- [`Changelog`](docs/changelog.md) records release changes and known limitations.
- [`docs/workflow-format.md`](docs/workflow-format.md) documents persistence,
  compatibility, and capability boundaries.

## Optional integrations

The `ml` extra enables the PyPlaid adapter and the `cosapp` extra enables the
CoSApp adapter. Neither extra is part of the minimum core support guarantee.
Install an extra only when its upstream dependency, license terms, platform
requirements, and integration behavior have been reviewed for the target
release:

```bash
uv sync --extra ml
uv sync --extra cosapp
```

Optional adapters may execute external tools or user-provided models. Treat
their workflows as trusted input and test the exact dependency versions before
production use.

## License

FlowGraph Core is licensed under the [BSD 3-Clause License](LICENSE). Release
compliance requires review of the exact dependency lockfile, build artifacts,
third-party notices, native dependencies, and applicable license obligations.