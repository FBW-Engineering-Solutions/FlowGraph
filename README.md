# FlowGraph Core

`FlowGraph` is the GUI-free Python workflow engine. It provides typed workflow
composition, validation, persistence, execution, adapters, mesh and image data
operations, browser-WASM execution support, and metadata-only catalog export
for compatible external clients.

> **Alpha status:** FlowGraph Core `0.1.x` is an alpha series for evaluation,
> development, experimentation, and early adopter feedback. APIs and workflow
> behavior may change before `1.0.0`. See [`Release Policy`](docs/policies/release-policy.md).

## Development

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
uv run flowgraph run workflow.json --input name=value
uv run flowgraph run workflow.json --override node-id.parameter=value
uv run flowgraph run workflow.json --json-output results.json
```

Workflows use the versioned `flowgraph-workflow` JSON format. Core validation and
execution are UI-independent.

## Package artifacts

Build the portable, pure-Python source distribution and wheel with:

```bash
uv build --out-dir dist/
```

The resulting wheel is compatible with all supported Python platforms. See
`packaging/README.md` for release details.

The initial supported publication channels are GitHub source releases and
PyPI. Conda, Docker, operating-system package managers, and third-party mirrors
are not supported release channels at this time. See
[`Release Channels`](docs/policies/release-channels.md) for the release policy.

FlowGraph Core declares Python 3.11 or newer. CI covers Python 3.11 and 3.13 on
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