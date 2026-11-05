# FlowGraph Core Release Channels

**Decision date:** September 22, 2026
**Scope:** FlowGraph Core alpha releases

## Supported channels

### GitHub source releases

GitHub Releases are the canonical source-release channel. Each release should
include:

- the version tag;
- the source distribution (`.tar.gz`);
- the Python wheel (`.whl`);
- SHA-256 digests exposed in release asset metadata (a separate public checksum
  manifest is optional);
- release notes and upgrade information;
- license and third-party-notice files when required; and
- SBOM artifacts when generated for the release.

### PyPI

PyPI is the canonical installation channel for Python users. Publish the
FlowGraph Core source distribution and wheel to the `flowgraph` project using
the reviewed release workflow. The release manager must verify account and
publisher protections separately; this policy does not establish their status.

PyPI publication must use the final BSD-3-Clause metadata, the Felipe Bordeu
author/maintainer metadata, the correct project URLs, and artifact validation
before upload.

## Unsupported distribution channels

Core release procedures do not provide publication or support through:

- Conda channels (the repository recipe was removed on November 5, 2026);
- Docker Hub or other container registries;
- operating-system package managers;
- private package indexes; or
- third-party release mirrors.

These channels may be considered later only after adding platform-specific
testing, ownership, security, provenance, support, and publication procedures.

## Source checkout usage

Users may clone the repository and build it locally with `uv`, but source
checkout usage is not a separate supported distribution channel. The supported
release artifacts are the GitHub source release and the PyPI package.

Optional Desktop and Web clients have separate distribution and validation
procedures; Core wheel/sdist checks do not establish client support.

## Publication ownership

Felipe Bordeu is the release manager. The current single-maintainer policy does
not require an independent backup owner. Release continuity depends on securing
the maintainer's GitHub and PyPI accounts, configuring account recovery, enabling MFA, and
retaining private release backups and artifact records.