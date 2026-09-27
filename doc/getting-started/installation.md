---
id: getting-started.installation
title: Installation
section: Getting Started
order: 20
---

# Installation

FlowGraph runs locally so it can access your files and execute workflows where your
data lives. The [FlowGraph Web Editor](https://www.fbw-es.com/flowgraph-editor) is an
authoring-only companion: use it to build and download versioned workflow JSON, then
use the binary FlowGraph package to inspect or execute that workflow.

## Requirements

- Python 3.10 or newer.
- [`uv`](https://docs.astral.sh/uv/) for installing FlowGraph and creating an isolated
  Python environment.

Install `uv` if it is not already available:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Windows, install `uv` using the installation instructions in the `uv`
documentation, then open a new terminal so the command is available on your `PATH`.

## Install the binary package from the package index

FlowGraph is distributed as a binary wheel through the package index. Create an
isolated environment and install the package by name:

```bash
uv venv
uv pip install flowgraph
```

`uv` selects the compatible binary wheel for your Python interpreter and operating
system. The current binary release targets CPython 3.11 through 3.14.

Run the installed command through the environment managed by `uv`:

```bash
uv run flowgraph --help
```

The binary package provides the headless `flowgraph` command for inspecting and
executing workflow JSON.

## Run temporarily with `uvx`

For a temporary installation without creating a persistent environment, run the
package directly with `uvx`:

```bash
uvx flowgraph
```

The `uvx` environment is temporary. Use the binary-wheel installation above when you
want a persistent FlowGraph environment.

## Inspecting and running a workflow

FlowGraph includes a headless command for inspecting and executing workflow JSON
without opening the graphical workspace. Check a workflow with:

```bash
uv run flowgraph inspect workflow.json
```

The Web Editor and local application use the same versioned `flowgraph-workflow` JSON
format. The editor does not execute workflows, read local files, perform mesh
operations, or run Python source from a User Function node. Download the workflow and
run it locally, for example:

```bash
uv run flowgraph run workflow.json
```

You can provide runtime inputs and parameter overrides without changing the workflow
file:

```bash
uv run flowgraph run workflow.json \
  --input in_filename=input.stl \
  --input out_filename=output.geo
```

Continue with [your first project](first-project.md).