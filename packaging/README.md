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

## Published-release evidence archive

The release manager archives evidence promptly after each intended publication,
before Actions logs or artifacts expire. Package artifacts have a 30-day download
window; the repository's Actions retention is currently 90 days. Neither is
durable storage. Keep public packages and notes on GitHub Releases, and retain
the complete evidence archive in maintainer-controlled backup storage outside
the repository, with a second independent copy, for the lifetime of the project.
Keep archives for yanked and superseded releases too. This procedure does not
assert that an archive or backup has already been created.

Retain the exact published wheel/sdist (not a rebuild), tag and commit SHA,
source snapshot including `pyproject.toml`, `uv.lock`, and workflow, lockfile hash,
Python/uv/build-tool versions, runner image information, installed dependency
inventory, complete relevant workflow logs and results for every run attempt,
and applicable audit/compliance outputs. Preserve relevant PR decisions, risk
review and environment approval evidence, plus GitHub and PyPI publication
metadata, timestamps and file hashes. Save separate prerequisite PR/branch runs
when relied upon; one tag run is not evidence of every review or earlier check.
Retain only actually generated compliance outputs; note unavailable evidence
explicitly rather than claiming that an SBOM or native audit exists.

The following Bash commands use an authenticated GitHub CLI, curl, Git, and uv
from the repository root. Set `TAG` to the published tag, `RUN_ID` to its exact
publishing workflow run, and `EVIDENCE_DIR` to a new absolute directory in your
external backup storage. Do not use an existing directory or overwrite an archive.
These commands download evidence; they do not create a release or upload to PyPI.

```bash
: "${TAG:?Set the published tag}" "${RUN_ID:?Set the publishing run ID}"
: "${EVIDENCE_DIR:?Set a new absolute external archive directory}"
REPO=FBW-Engineering-Solutions/FlowGraph
mkdir "$EVIDENCE_DIR" || exit 1
mkdir "$EVIDENCE_DIR/packages"
gh api "repos/$REPO/actions/runs/$RUN_ID" > "$EVIDENCE_DIR/run.json"
SHA=$(gh api "repos/$REPO/actions/runs/$RUN_ID" --jq .head_sha)
ATTEMPTS=$(gh api "repos/$REPO/actions/runs/$RUN_ID" --jq .run_attempt)
git rev-parse "$TAG^{commit}"
printf 'Publishing commit: %s\n' "$SHA"
# Stop if the tag's commit differs from SHA or run.json is not the intended tag run.
git archive --format=tar --output="$EVIDENCE_DIR/source.tar" "$SHA"
git show "$SHA:uv.lock" > "$EVIDENCE_DIR/uv.lock"
gh api "repos/$REPO/releases/tags/$TAG" > "$EVIDENCE_DIR/github-release.json"
gh release download "$TAG" --repo "$REPO" --dir "$EVIDENCE_DIR/packages"
for attempt in $(seq 1 "$ATTEMPTS"); do
  gh api "repos/$REPO/actions/runs/$RUN_ID/attempts/$attempt" \
    > "$EVIDENCE_DIR/attempt-$attempt.json"
  gh api --paginate --jq '.jobs[]' \
    "repos/$REPO/actions/runs/$RUN_ID/attempts/$attempt/jobs?per_page=100" \
    > "$EVIDENCE_DIR/jobs-$attempt.jsonl"
  gh api "repos/$REPO/actions/runs/$RUN_ID/attempts/$attempt/logs" \
    > "$EVIDENCE_DIR/logs-$attempt.zip"
done
VERSION=${TAG#v}
curl --fail --silent --show-error "https://pypi.org/pypi/flowgraph/$VERSION/json" \
  > "$EVIDENCE_DIR/pypi-release.json"
```

Check every command for failure; empty files or an unavailable log download are
not successful evidence capture. Inspect the metadata to confirm the repository,
tag, commit, workflow, run attempts and publication results. Download and compare
the PyPI wheel/sdist if necessary: their filenames and SHA-256 hashes must match
the exact saved packages and GitHub metadata. Investigate any mismatch; never
silently substitute a rebuilt artifact. Save the relevant review/approval and
risk records alongside these downloads (keep sensitive records private).

After adding all records, generate a local integrity manifest. This manifest
supports backup verification; it is not a signature or proof of provenance.

```bash
uv run --no-sync python - "$EVIDENCE_DIR" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
hashes = {}
for path in sorted(root.rglob("*")):
    if path.is_file() and path != root / "SHA256.json":
        with path.open("rb") as stream:
            hashes[path.relative_to(root).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
with (root / "SHA256.json").open("x", encoding="utf-8") as stream:
    json.dump(hashes, stream, indent=2)
    stream.write("\n")
PY
```

Verify the archive is readable (including log ZIPs and source TAR), compare its
manifest with the independent publication hashes, and copy the complete archive
to a second independent backup location. Recompute hashes from that second copy
and compare with `SHA256.json`; confirm a restore/read succeeds. Record archive
locations, capture date, verification result and any missing evidence in the
private release record. Do not put credentials, recovery codes or local backup
paths into public release notes. A successful CI run does not verify these backups.

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