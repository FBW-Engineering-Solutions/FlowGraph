# FlowGraph Core Release Channels

**Decision date:** September 22, 2026
**Scope:** Initial public FlowGraph Core release

## Supported channels

### GitHub source releases

GitHub Releases are the canonical source-release channel. Each release should
include:

- the version tag;
- the source distribution (`.tar.gz`);
- the Python wheel (`.whl`);
- SHA-256 checksums;
- release notes and upgrade information;
- license and third-party-notice files when required; and
- SBOM artifacts when generated for the release.

### PyPI

PyPI is the canonical installation channel for Python users. The project will
publish the FlowGraph Core source distribution and wheel to the `flowgraph`
project using the protected project owner account and a reviewed release
workflow.

PyPI publication must use the final BSD-3-Clause metadata, the Felipe Bordeu
author/maintainer metadata, the correct project URLs, and artifact validation
before upload.

### Conda channel

The repository provides a `conda-build` recipe at
`packaging/conda/meta.yaml`, and FlowGraph is distributed through the
[`flowgraph` Anaconda channel](https://anaconda.org/channels/flowgraph). Users
can install it with:

```bash
conda install -c flowgraph flowgraph
```

The recipe is a supported packaging input and must be validated against the
published source distribution and a clean Conda environment before each release
claims Conda compatibility. The `flowgraph` channel is separate from
conda-forge; recipe inclusion does not imply that `flowgraph` is available on
conda-forge.

## Not supported for the initial release

The initial public release does not promise or publish through:

- Docker Hub or other container registries;
- operating-system package managers;
- private package indexes; or
- third-party release mirrors.

These channels may be considered later only after adding platform-specific
testing, ownership, security, provenance, support, and publication procedures.

## Source checkout usage

Users may clone the repository and build it locally with `uv`, but source
checkout usage is not a separate supported distribution channel. The supported
release artifacts are the GitHub source release, the PyPI package,
and the `flowgraph` Conda channel package.

## Publication ownership

Felipe Bordeu is the initial and current release manager. The project is
maintained by one developer, so no independent backup owner is required for the
initial alpha release. Release continuity depends on securing the maintainer's
GitHub and PyPI accounts, configuring account recovery, enabling MFA, and
retaining private release backups and artifact records.