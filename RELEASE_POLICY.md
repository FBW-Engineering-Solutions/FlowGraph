# FlowGraph Core Release Policy

**Decision date:** September 20, 2026  
**Current series:** `0.1.x` alpha

## Current release status

The `0.1.x` series is an **alpha** series. FlowGraph Core is usable for
evaluation, development, experimentation, and early adopter feedback, but it is
not a stable API commitment.

Alpha status means:

- public APIs may change between releases;
- workflow JSON behavior and schemas may evolve;
- undocumented behavior and internal modules may change without notice;
- dependency, platform, and performance support remains limited by the support
  policy and CI evidence;
- users should maintain backups of important workflows and pin versions for
  reproducible environments; and
- support and maintenance are best effort.

Every alpha release must include release notes describing API changes,
workflow-format changes, dependency changes, known limitations, security fixes,
and migration actions where applicable.

## Versioning

FlowGraph uses Semantic Versioning conventions as a guide, with the normal
pre-1.0 qualification that `0.y.z` releases may include breaking changes. The
version in `pyproject.toml` is the source of truth for package artifacts.

- Increment the patch component for compatible fixes and small improvements.
- Increment the minor component when adding features or making broader changes;
  minor `0.x` releases may still require migration work.
- Reserve `1.0.0` for a deliberate stability milestone, not merely a calendar
  date or package-publication event.

## Alpha release requirements

Before publishing an alpha release:

- pass the applicable CI matrix and local quality gates;
- build and inspect the source distribution and wheel;
- publish release notes and known limitations;
- validate license, dependency, artifact, and SBOM requirements through the
  release compliance pipeline;
- document workflow-format changes and migration guidance; and
- verify the release through the supported GitHub and PyPI channels.

The open-source release checklist remains authoritative when it imposes stricter
requirements than this policy.

## Release operations

The release manager must retain the source commit, signed tag when available,
locked-environment hash, build logs, artifact hashes, checksums, compliance
compliance outputs, approvals, and publication time. A failed or compromised
release must
be stopped, the relevant PyPI version yanked or superseded when appropriate,
GitHub assets corrected, exposed credentials rotated, and a replacement release
documented in the changelog. Release automation uses GitHub-hosted runners and
trusted publishing/MFA procedures rather than long-lived package credentials.

Dependency updates, license/SBOM rescans, secret scans, support-matrix reviews,
and release rehearsals should be scheduled at least monthly while the project
remains in alpha.

## Promotion criteria

The project may consider a beta series when the public API and workflow format
have been exercised by external users, the supported platform matrix has stable
passing coverage, release and security processes are operational, and the major
license/dependency blockers are resolved.

A stable `1.0.0` release should additionally require an intentional API and
workflow-format compatibility commitment, documented support lifecycle, tested
release rollback/recovery, and sufficient maintainer continuity.