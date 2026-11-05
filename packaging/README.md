# FlowGraph Core Packaging

This repository owns distributable `flowgraph` core wheels. The core package is
GUI-free: it provides the workflow engine, adapters, domain model, persistence,
test data, catalog exporter, and the headless `flowgraph` command.

## Release package

```bash
uv sync --extra dev --extra io
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
independently on Ubuntu, Windows, and macOS with Python 3.11, 3.12, 3.13, and 3.14. Manual
`workflow_dispatch` runs also rehearse packaging without publishing, even when
dispatched against a tag. Only an actual version-tag **push** can start release
validation and publication. Do not push a release tag just to test packaging.

Each of the 24 artifact-test jobs creates a fresh environment outside the
checkout, installs the selected archive with its declared dependencies, checks
dependency consistency, verifies installed versions/import locations, reads
packaged image/workflow resources, and exercises workflow persistence and the
installed CLI's help, inspection, and execution with an expected JSON result.
The build uses isolation and `--no-sources`; archive installations resolve
runtime dependencies independently of the development lockfile.

Run the same checks locally from the repository root:

```bash
uv build --no-sources --out-dir .validation-dist/rehearsal
uv run python packaging/test_artifact.py --artifacts .validation-dist/rehearsal --kind wheel
uv run python packaging/test_artifact.py --artifacts .validation-dist/rehearsal --kind sdist
```

Use a new, empty output directory per rehearsal; if `.validation-dist/rehearsal`
already contains artifacts, choose a different empty subdirectory under the
ignored `.validation-dist/` directory and use it in all three commands. Artifact
output may be inside the checkout; the runner creates its installation and smoke
test environments outside the checkout. Python 3.11+ and `uv` on PATH
are required; network access is needed for uncached dependencies/build tools.
The commands do not upload anything. CI archives are retained for one day.

Both production publication jobs wait for the complete artifact matrix and tag
validation, then use the same named artifacts from that workflow run. Required
human approvals must be configured separately in GitHub environment settings;
the workflow alone does not establish those protections. This rehearsal does
not validate optional extras, every workflow, or byte reproducibility.

## Release procedure

### Dependency audit scope

After the locked test-environment installation, each CI matrix job snapshots all
installed Python distributions with the project interpreter. This includes its
selected extras, transitive dependencies, and development/test tools. Only the
local FlowGraph project is excluded from the package-advisory lookup; its version
is logged separately. The interpreter, environment prefix, exact pins and package
count are printed in the job log. The requirements file is temporary CI output,
not a durable release-evidence archive.

To reproduce against an already synchronized project environment, run from the
repository root:

```bash
uv run --no-sync python packaging/audit_requirements.py --output .validation-dist/audit-requirements.txt
uvx --from pip-audit pip-audit --requirement .validation-dist/audit-requirements.txt --no-deps --disable-pip --strict
```

The isolated audit tool reads the explicit inventory instead of auditing its own
environment. Exact pins and disabled dependency resolution prevent it from
selecting different package versions. Collection errors and vulnerability findings
fail CI; do not suppress them or automatically modify dependencies. Network access
to the advisory service is required. A local snapshot reflects the local installed
environment, not necessarily every CI job's extras or platform selection.

This checks known Python-package advisories, not all native libraries, Java
components, optional clients, or uninstalled integrations. An empty findings list
does not establish security or license compliance.

### Build and publication

Version `0.1.8` is the planned first MVP baseline. This is not a publication
announcement or a stable API commitment; the `0.1.x` series remains alpha.
Pre-MVP releases are outside this release-readiness documentation scope.

The version in `pyproject.toml` is the artifact version source of truth and
`docs/changelog.md` is the release-note source of truth. From a clean checkout:

```bash
uv sync --locked --extra dev --extra io
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
Choose a new, unused tag/version for corrections; do not move existing release
tags to include later fixes or reuse a published version for different bytes.

Inspect both artifacts, install them in clean environments, run `flowgraph
--help`, import `flowgraph`, and exercise a representative workflow before
publishing. Retain dependency notices, SBOM, native
audit, preserved license texts, and checksums with the release record. Publish
through GitHub Releases and PyPI only after applicable release checks pass and
relevant unresolved risks have been reviewed and recorded. Optional improvements
are not automatic release blockers. Required security and artifact reviews still
apply. Core package validation does not validate optional Desktop or Web clients.

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