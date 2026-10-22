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

## Non-publishing GitHub CI rehearsal

Push a normal branch (without tags), or open a pull request. The workflow runs
source tests, builds one wheel/sdist pair, and tests each downloaded distribution
independently on Ubuntu, Windows, and macOS with Python 3.11 and 3.13. Manual
`workflow_dispatch` runs also rehearse packaging without publishing, even when
dispatched against a tag. Only an actual version-tag **push** can start release
validation and publication. Do not push a release tag just to test packaging.

Each of the 12 artifact-test jobs creates a fresh environment outside the
checkout, installs the selected archive with its declared dependencies, checks
dependency consistency, verifies installed versions/import locations, reads
packaged image/workflow resources, and exercises workflow persistence and the
installed CLI's help, inspection, and execution with an expected JSON result.
The build uses isolation and `--no-sources`; archive installations resolve
runtime dependencies independently of the development lockfile.

Run the same checks locally from `/home/fbw/repos/FlowGraph/FlowGraph`:

```bash
uv build --no-sources --out-dir /tmp/flowgraph-rehearsal-artifacts
python packaging/test_artifact.py --artifacts /tmp/flowgraph-rehearsal-artifacts --kind wheel
python packaging/test_artifact.py --artifacts /tmp/flowgraph-rehearsal-artifacts --kind sdist
```

Use a new, empty output directory per rehearsal. Python 3.11+ and `uv` on PATH
are required; network access is needed for uncached dependencies/build tools.
The commands do not upload anything. CI archives are retained for one day.

Both production publication jobs wait for the complete artifact matrix and tag
validation, then use the same named artifacts from that workflow run. Required
human approvals must be configured separately in GitHub environment settings;
the workflow alone does not establish those protections. This rehearsal does
not validate Conda, optional extras, every workflow, or byte reproducibility.

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

See `docs/release-reconciliation.md` for the October 22, 2026 audit: historical
GitHub tags `v0.1.2.1`, `v0.1.3`, and `v0.1.4` attach packages labeled `0.1.2`.
Source `0.1.5` is not proof of a PyPI publication. Historical tags and assets
are preserved rather than silently replaced.

The version in `pyproject.toml` is the artifact version source of truth and
`docs/changelog.md` is the release-note source of truth. From a clean checkout:

```bash
uv sync --locked --extra dev
uv run ruff format --check .
uv run ruff check .
uv run pytest --cov=flowgraph --cov-report=term-missing
rm -rf dist/
uv build --out-dir dist/
python packaging/check_release.py --artifacts dist/ --tag "v$(python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
```

The validator compares source declarations, filenames, and internal wheel/sdist
metadata to the exact tag. Omit `--tag` only for untagged development builds.
CI validates downloaded artifacts before either GitHub or PyPI publication.
Choose a new, unused tag/version for corrections; `v0.1.5` already exists and
must not be moved to include later fixes.

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
bad PyPI release where appropriate, adding an explicit warning to the GitHub
release notes, rotating affected credentials where necessary, and publishing a
clearly documented fix under a new, unused version/tag. Preserve historical tags
and assets; never silently replace or relabel published files. Any exceptional
asset removal must be explicitly documented with the reason and original hashes.