---
id: getting-started.installation
title: Installation
section: Getting Started
order: 20
---

# Installation

FlowGraph Core provides Python APIs and the headless `flowgraph` command to inspect
and execute workflow JSON locally. Browser and desktop clients are separate;
installing Core does not install a workflow editor. Only run workflows you trust:
native Python execution is not sandboxed.

## Requirements

- Python 3.11 or newer (`requires-python = ">=3.11"`).
- [`uv`](https://docs.astral.sh/uv/) for installing FlowGraph and creating an isolated
  Python environment.

Follow the [uv installation instructions](https://docs.astral.sh/uv/getting-started/installation/)
for your operating system, then open a new terminal if needed to put `uv` on your
`PATH`.

Core is distributed as a **pure-Python wheel** and a source distribution. Its
scientific dependencies, including VTK and Muscat, can contain native libraries
and impose additional platform or build requirements. A portable Core wheel does
not guarantee that every dependency or optional integration supports every system.
The current CI targets Python 3.11–3.14 on Ubuntu, Windows, and macOS; this is a
tested-version target, not an upper bound in the Python requirement. Release
support depends on the exact candidate's passing jobs; see the
[support policy](https://github.com/FBW-Engineering-Solutions/FlowGraph/blob/master/docs/policies/support-policy.md).

## Persistent installation from the package index

Start in a new directory **outside any source checkout or uv project**. For example,
the following commands create a working directory and select Python 3.13, one of
the tested targets. You can select another supported interpreter with `--python`.

```bash
mkdir flowgraph-work
cd flowgraph-work
uv venv --python 3.13
uv pip install flowgraph
uv run --no-project flowgraph --help
```

Stay in this directory for the persistent-installation examples below. `uv pip`
installs into its `.venv`; `uv run --no-project` uses that environment without
discovering or syncing a parent uv project. No shell-specific activation command
is needed. See [uv's environment documentation](https://docs.astral.sh/uv/pip/environments/)
and [command reference](https://docs.astral.sh/uv/reference/cli/#uv-run).

These commands install a published package, not the current Git checkout or its
lockfile. To reproduce a particular published release, use an explicit version
such as `flowgraph==VERSION`, replacing `VERSION` with the desired published version.

## Optional runtime integrations

Install extras into the same persistent environment when a workflow needs them.
The `io` extra supplies meshio, Meshlane, pandas, h5py, Pillow, and openpyxl for
mesh, table, and image operations:

```bash
uv pip install 'flowgraph[io]'
```

Other runtime extras are:

| Extra | Purpose and additional requirements |
| --- | --- |
| `io` | Mesh, table, and image libraries listed above; individual formats can need additional backends. |
| `imagej` | PyImageJ and scyjava; a suitable Java runtime and the selected ImageJ/Fiji components are needed. Initialization may download Java artifacts. |
| `ml` | PyPlaid integration; its own dependencies and platform constraints apply. |
| `cosapp` | CoSApp model integration; user models can require other libraries or external tools. |

For example, request the ImageJ integration with:

```bash
uv pip install 'flowgraph[imagej]'
```

Installing an extra does not certify an external runtime, plugin, model, or every
platform combination. Check the relevant adapter documentation and upstream
requirements. Only install extras whose dependencies and license terms fit your
environment. See [Third-Party Notices](../reference/third-party-notices.md).

## Development from a source checkout

From the root of a cloned Core repository, use the project's declared dependencies
and lockfile instead of the package-index instructions above:

```bash
uv sync --locked --extra io
uv run flowgraph --help
```

For development and the full test suite:

```bash
uv sync --locked --extra dev --extra io
uv run pytest
```

`uv sync` manages the checkout's project environment; it is not the way to add an
extra to the standalone installation above. Extra integration tests may need their
own dependencies; see the
[contribution guide](https://github.com/FBW-Engineering-Solutions/FlowGraph/blob/master/.github/CONTRIBUTING.md).

## Run temporarily with `uvx`

To run the published tool without maintaining a local `.venv`, use explicit
subcommands with `uvx`:

```bash
uvx --python 3.13 flowgraph --help
uvx --python 3.13 flowgraph inspect workflow.json
uvx --python 3.13 flowgraph run workflow.json
```

`uvx` uses an isolated, cached tool environment, not the persistent `.venv` or
checkout dependencies. Request extras separately for that environment, for example:

```bash
uvx --python 3.13 --from 'flowgraph[io]' flowgraph run workflow.json
```

These workflow commands require an existing file and any runtime inputs it needs.
For repeatable tool selection, pin the package with `--from 'flowgraph==VERSION'`
(or `--from 'flowgraph[io]==VERSION'`). Replace `VERSION` with a published version.
See [uv tools](https://docs.astral.sh/uv/guides/tools/).

## Inspecting and running a workflow

The following examples use the persistent installation directory created above.
Place a saved, trusted workflow there, or supply its path. `workflow.json`, input
names, and node IDs below are illustrative: replace them with those in your file.
Inspection does not execute the workflow:

```bash
uv run --no-project flowgraph inspect workflow.json
```

Inspection shows a compact interface summary by default. Add `--full` or `-f`
to include the workflow graph.

Run the workflow locally:

```bash
uv run --no-project flowgraph run workflow.json
```

You can provide runtime inputs and parameter overrides without changing the workflow
file:

```bash
uv run --no-project flowgraph run workflow.json --input text=hello -i label=example --override source.value=updated --json-output outputs.json
```

`-i` is an alias for `--input`. Use either form repeatedly to set multiple
published workflow inputs. In the example, `text` and `label` are published input
names, while `source.value` means parameter `value` on node ID `source`.
`--json-output` writes the public outputs to a JSON file. These settings apply only
to this invocation; they do not rewrite the workflow file. In a source checkout,
use `uv run flowgraph ...` instead of `uv run --no-project flowgraph ...`.

If an input is omitted, the runner looks for its downstream node's saved parameter
value and emits a warning to stderr when it uses that value. This includes nested
workflow inputs and directly exported parameters. Inputs with no usable saved
value, or with conflicting downstream values, must be supplied explicitly.
See [Omitted inputs and saved parameter values](../user-guide/workflows.md#omitted-inputs-and-saved-parameter-values)
for details. Fallbacks do not modify the saved workflow file.

Continue with [your first project](first-project.md).