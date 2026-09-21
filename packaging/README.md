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
```

`uv build` produces the source distribution and a platform-independent,
pure-Python wheel. No Cython compiler, native extension build, or platform wheel
repair step is required.

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
publishing. Retain dependency notices, SBOM, native audit, preserved license
texts, and checksums with the release record. Publish through GitHub Releases
and PyPI only after the release blockers in `TODO.md` and the compliance review
are closed.

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