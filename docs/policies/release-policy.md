# FlowGraph Core Release Policy

**Decision date:** September 20, 2026  
**Current series:** `0.1.x` alpha

## Current release status

Version `0.1.8` is the planned first MVP baseline, not a publication announcement
or a stable API commitment. Pre-MVP releases are outside this release-readiness
documentation scope.

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

The release tag must be exactly `v` followed by that version. Validate both
artifact filenames and internal wheel/sdist metadata with
`packaging/check_release.py` before publication. Source declarations, release tags,
artifact filenames, and internal package metadata must agree.

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

Apply these requirements to each release candidate. Review and record relevant
unresolved security, dependency, licensing, and support risks before publication.
Unrelated owner decisions and optional improvements do not automatically block
a release.

## Release operations

Create release tags only from an exact commit already merged into `master` with
a successful Core CI run for that commit. Confirm the commit and its hosted
checks before pushing a new tag; permission to create tags is not evidence that
the target was reviewed or validated. The single maintainer performs this
verification. Tag-push artifact/version validation remains required before either
GitHub or PyPI publication. See the [governance guide](../maintainers/governance.md)
for the approved branch/tag rules and pending remote rollout.

The release manager must archive the exact source commit and tag, source/build
configuration and lockfile hash, build environment, all relevant run-attempt logs
and results, exact published packages and hashes, applicable compliance outputs,
reviews, approvals, and publication metadata/times promptly after publication.
Keep the complete archive in maintainer-controlled storage outside the repository,
with a second independent verified copy, for the lifetime of the project,
including yanked or superseded releases. GitHub Releases retain public packages
and notes; expiring Actions artifacts/logs are not durable evidence storage.
Follow the [evidence archive procedure](../../packaging/README.md#published-release-evidence-archive)
and record capture/restore verification privately. Defining this policy does not
establish that a backup exists. A failed or compromised release must
be stopped, the relevant PyPI version yanked or superseded when appropriate,
GitHub release notes annotated, exposed credentials rotated, and a replacement release
documented in the changelog. Release automation uses GitHub-hosted runners and
trusted publishing/MFA procedures rather than long-lived package credentials.

Never silently replace or relabel published assets, reuse a published package
version for different bytes, or move an existing tag. Publish corrections under
a new, unused version/tag. Preserve historical assets; document any exceptional
removal with its reason and original hashes.

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