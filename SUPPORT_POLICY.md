# FlowGraph Core Support Policy

**Decision date:** September 20, 2026  
**Scope:** Initial public FlowGraph Core release

This is the initial best-effort support policy for the standalone, GUI-free core
package. It describes what the project intends to support; it does not override
the dependency requirements or guarantee that every dependency works on every
platform. The current `0.1.x` series is alpha, so these support statements are
initial targets rather than a stable API commitment.

## Python versions

FlowGraph Core declares `requires-python = ">=3.11"` and initially supports
Python 3.11 and newer versions that are compatible with the declared dependency
set.

The CI workflow is configured to test Python 3.11 and 3.13. Other Python 3.11+
versions are declaration-level support targets until they are added to the CI
matrix and verified. A release must not claim that every Python version has been
tested until that matrix exists.

## Operating systems and architectures

The CI workflow is configured for GitHub-hosted Ubuntu, Windows, and macOS
runners. These platforms become verified support targets only after the
corresponding matrix jobs pass for the release candidate. Other Linux
architectures and distributions may work, but are not individually guaranteed.

The project does not claim platform support for an operating-system/Python
combination whose CI job has failed or has not run successfully for the release
candidate.

FlowGraph Core is distributed as a platform-independent Python wheel, but its
scientific dependencies may provide platform-specific native libraries and may
impose additional operating-system or architecture requirements.

## Runtime dependencies

The required runtime dependency set is defined by `pyproject.toml` and resolved
for development and release verification through `uv.lock`. Supported behavior
assumes that these dependencies can be installed from their declared package
indexes and that their own platform requirements are satisfied.

The optional `ml` and `cosapp` extras are not part of the minimum core support
guarantee. They are supported only when their exact dependencies are available
and the relevant integration has been tested for the release.

## Compatibility guarantees

- The public Python API is pre-1.0 and may change between `0.1.x` releases.
- The `flowgraph-workflow` JSON format is versioned and should remain readable
  across compatible releases where practical.
- Changes that intentionally break workflow-file compatibility must be described
  in release notes and include migration guidance when feasible.
- No guarantee is made that undocumented internals, private symbols, exception
  wording, or incidental serialized fields remain stable.
- Bug fixes should preserve documented behavior unless the previous behavior was
  unsafe, invalid, or clearly unintended.

## Deprecation policy

When practical, a public feature or behavior scheduled for removal will be
documented in release notes and marked as deprecated before removal. The project
does not currently promise a fixed number of releases or months between
deprecation and removal because it is an early-stage pre-1.0 project maintained
by one initial maintainer.

Security fixes, dependency removals, and urgent correctness changes may require
shorter timelines. Such changes must be explained in the release notes.

## Maintenance policy

Maintenance is best effort. The latest public release receives priority for bug
and security fixes. Older releases may receive fixes only when the issue is
security-critical, low-risk to backport, or required by a supported dependency
change.

There is no guaranteed response time, uptime, commercial support agreement, or
long-term maintenance period. See `SUPPORT.md` and `SECURITY.md` for support and
security-reporting channels.

## Unsupported use cases

The initial public core release does not promise support for:

- GUI or native desktop behavior from this repository;
- Windows, macOS, or unverified Linux architectures as supported platforms;
- optional integrations that have not been tested for the release;
- production execution of arbitrary user code, external tools, or untrusted
  workflows without independent security review;
- undocumented internal APIs or private package modules; or
- a specific performance, memory, throughput, or availability level.

This policy can be revised when the CI matrix, maintainer team, dependency
review, and release process provide evidence for broader support.