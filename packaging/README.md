# FlowGraph Core Packaging

This repository owns distributable `flowgraph` core wheels. The core package is
GUI-free: it provides the workflow engine, adapters, domain model, persistence,
test data, catalog exporter, and the headless `flowgraph` command.

## Release package

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv build --out-dir dist/
```

The generated `flowgraph` wheel exposes:

```bash
flowgraph inspect workflow.json
flowgraph run workflow.json --input name=value --override node.parameter=value
flowgraph run workflow.json -i name=value --override node.parameter=value
```

`-i` is an alias for `--input`, and either option can be repeated for multiple
published workflow inputs.

`uv build` produces the source distribution and a platform-independent,
pure-Python wheel. No Cython compiler, native extension build, or platform wheel
repair step is required.

## Conda recipe

The repository includes a `conda-build` recipe in `packaging/conda/meta.yaml`.
It packages the published Python source distribution as a `noarch: python`
package and maps the runtime dependencies to their Conda package names. The
recipe deliberately installs with `--no-deps` so Conda remains the dependency
resolver rather than mixing Conda and PyPI installations.

Build and inspect it with `conda-build` from an environment that has access to
the required dependency channels:

```bash
conda install -c conda-forge conda-build
conda build packaging/conda
```

FlowGraph packages are distributed through the [`flowgraph` Anaconda
channel](https://anaconda.org/channels/flowgraph). Install the package with:

```bash
conda install -c flowgraph flowgraph
```

The recipe and channel publication are separate release operations. Each
release still requires maintainer approval and validation of the complete native
dependency graph.

## Release procedure

The version in `pyproject.toml` is the artifact version source of truth and
`docs/changelog.md` is the release-note source of truth. From a clean checkout:

```bash
uv sync --locked --extra dev
uv run ruff format --check .
uv run ruff check .
uv run pytest --cov=flowgraph --cov-report=term-missing
rm -rf dist/
uv build --out-dir dist/
```

Inspect both artifacts, install them in clean environments, run `flowgraph
--help`, import `flowgraph`, and exercise a representative workflow before
publishing. For Conda, also inspect the built package in a clean Conda
environment and run the recipe tests. Retain dependency notices, SBOM, native
audit, preserved license texts, and checksums with the release record. Publish
through GitHub Releases, PyPI, and the reviewed `flowgraph` Conda channel only
after the release blockers in `TODO.md` and the compliance review are closed.

## Reproducibility limitations

The wheel and source archive are intended to be portable, but consecutive local
`uv build` runs are not currently byte-for-byte identical. Release evidence must
therefore record exact artifact hashes, the commit, Python/build environment,
lockfile hash, and generation time. Do not claim reproducible builds until a
future build-normalization change and independent verification demonstrate that
property. Known possible nondeterminism includes archive member timestamps,
wheel metadata ordering, setuptools behavior, and dependency-generated content.

Release rollback consists of stopping publication, yanking or superseding a
bad PyPI release where appropriate, deleting or correcting the GitHub release
assets, rotating affected credentials, and publishing a clearly documented fix.
manual review of package metadata, native libraries, generated code, and
upstream notices.