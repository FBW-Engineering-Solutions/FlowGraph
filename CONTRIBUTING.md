# Contributing to FlowGraph Core

Thank you for contributing to the GUI-free FlowGraph Core package. Contributions
must preserve the headless import boundary, workflow-format contracts, and BSD
3-Clause licensing requirements.

## Prerequisites

- Python 3.11 or newer.
- [`uv`](https://docs.astral.sh/uv/) for environments and project commands.
- Git and a working C/C++ runtime environment suitable for the scientific Python
  dependencies on the target platform.

Set up a locked development environment from the repository root:

```bash
uv sync --locked --extra dev
```

## Development checks

Run the complete local quality gate before opening a pull request:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run python -m compileall -q src tools tests
```

Run `uvx ty check src` when changing public APIs or type-sensitive application
code. Existing third-party typing diagnostics are tracked in `TODO.md`; new
diagnostics should not be introduced without an explanation.

## Code and documentation style

- Keep core modules independent of GUI frameworks and private sibling projects.
- Use built-in generic annotations and `Type | None` syntax for Python 3.11+.
- Use NumPy-style docstrings for public functions, classes, and changed behavior.
- Add focused pytest coverage for new behavior, error paths, and security
  boundaries. Prefer real objects over mocks.
- Update `README.md`, `Architecture.md`, `CHANGELOG.md`, or the relevant policy
  document when user-visible behavior changes.
- Do not add repetitive source-file copyright headers. The root `LICENSE` is the
  authoritative project notice; preserve notices in copied or adapted material.

## Workflow and persistence changes

Workflow JSON is a public, versioned interface. Changes must document the format
version, compatibility behavior, migration path, and handling of unknown nodes
or parameters. Add malformed-input and round-trip tests where applicable.

## Pull requests

Pull requests should:

1. Explain the problem and the chosen design.
2. Identify behavior, API, workflow-format, dependency, licensing, or security
   impacts.
3. Include tests and documentation updates.
4. Include a changelog entry for user-visible changes.
5. Confirm that no secrets, private paths, generated local state, or unrelated
   artifacts are included.
6. Use a signed-off commit when contributing under the DCO policy below.

Maintainers may request smaller commits, additional platform checks, release
evidence, or provenance information before merging.

## Developer Certificate of Origin

FlowGraph Core uses the Developer Certificate of Origin (DCO), not a separate
Contributor License Agreement. Each commit must include a sign-off line using
the contributor's real name and email, for example:

```text
Signed-off-by: Jane Developer <jane@example.org>
```

Use `git commit -s` to add the line. By signing, you certify the contribution
under the terms in [`DCO.md`](DCO.md). Do not sign on behalf of another person.

## Release notes

The release manager maintains `CHANGELOG.md` using Keep a Changelog headings.
User-visible changes, breaking behavior, security fixes, dependency changes,
workflow-format changes, and migration guidance belong in the changelog before
release artifacts are built.