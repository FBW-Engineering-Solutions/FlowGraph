# Open-Source Release TODO

> Release gate for publishing FlowGraph Core. Complete every **Blocker** before
> making the repository public. Record the owner, evidence, decision, and date
> for each completed item in the related issue or pull request.
>
> This checklist is an engineering and release-management aid, not legal advice.

## 0. Define scope, ownership, and release policy

- [x] **Decision recorded (September 19, 2026):** Publish only FlowGraph Core in
  this release. Companion applications and administrative tooling are not part
  of the public Core project, release, or support commitment.
- [x] Remove or rewrite all public-facing references to private companion
  projects. Core installation, examples, tests, documentation, CI, packaging,
  and support do not require them.
- [ ] **Blocker** Confirm the public project name, PyPI distribution name
  (`flowgraph`), Python namespace (`flowgraph`), organization, logo, domain, and
  social handles are available and do not infringe another party's trademarks.
  Preliminary findings and the remaining actions are recorded in
  `BRAND_REVIEW.md`; do not mark this item complete based only on package or
  repository availability.
- [x] **Decision recorded (September 20, 2026):** Felipe Bordeu owns the
  original FlowGraph Core code and has authority to publish it under the
  BSD-3-Clause license. FBW Engineering Solutions is Felipe Bordeu's freelance
  working name, not a separate rights holder.
- [x] **Decision recorded (September 20, 2026):** The initial supported
  publication channels are GitHub source releases and PyPI. Conda-forge, Docker,
  operating-system package managers, private indexes, and third-party mirrors
  are out of scope for the initial release. See `RELEASE_CHANNELS.md`.
- [x] **Decision recorded (September 20, 2026):** Felipe Bordeu is the initial
  maintainer, release manager, security contact, and escalation contact. Public
  support uses GitHub Issues; private vulnerability reports use GitHub private
  vulnerability reporting. See `SUPPORT.md` and `SECURITY.md`.
- [x] **Decision recorded (September 21, 2026):** FlowGraph is initially
  maintained by one developer. An independent backup owner is not required for
  the initial alpha release. The maintainer must enable MFA, configure account
  recovery, retain private repository backups, and preserve release records.
- [x] **Decision recorded (September 20, 2026):** Initial support is Python
  `>=3.11`. CI is configured for Python 3.11 and 3.13 on GitHub-hosted Ubuntu,
  Windows, and macOS runners; each platform/version combination must pass its
  release-candidate job before support is claimed. Python 3.10, other
  architectures, optional integrations, GUI behavior, undocumented APIs, and
  production guarantees for arbitrary user code are out of scope. Terms are in
  `SUPPORT_POLICY.md`.
- [x] **Decision recorded (September 20, 2026):** The `0.1.x` series is an
  alpha series. It is suitable for evaluation and early adopters but does not
  provide a stable API or workflow-format commitment. See `RELEASE_POLICY.md`.

## 1. License, copyright, and intellectual-property review

- [x] **Decision recorded (September 20, 2026):** License original FlowGraph
  Core work under BSD-3-Clause. The permissive license permits commercial and
  proprietary downstream use while requiring preservation of copyright, license,
  disclaimer, and non-endorsement terms.
- [x] Add the authoritative BSD 3-Clause license text as `/LICENSE`.
- [x] Replace `license = "LicenseRef-Proprietary"` in `pyproject.toml` with
  `BSD-3-Clause` and include `LICENSE` in built distributions.
- [ ] **Blocker** Ensure GitHub settings, README, PyPI metadata, wheel/sdist
  metadata, and release assets all state the same license.
- [x] **Decision recorded (September 20, 2026):** Felipe Bordeu owns the
  original FlowGraph Core work and has authority to publish it under BSD-3-Clause.
  FBW Engineering Solutions is Felipe Bordeu's freelance working name, not a
  separate third-party rights holder.
- [ ] **Blocker** Establish provenance and publication permission for every
  third-party code, documentation, asset, fixture, or contribution. Obtain
  compatible licenses or written permissions where needed.
- [x] **Decision recorded (September 20, 2026):** FlowGraph Core uses a
  centralized copyright-notice policy. The root `LICENSE` is authoritative;
  individual source, test, tool, documentation, example, and generated files do
  not require copyright or SPDX headers. Preserve legally required notices in
  copied or adapted third-party material.
- [ ] Audit source, tests, docs, diagrams, screenshots, examples, icons, and
  generated files for copied or restricted content. Replace, remove, or license
  every item that is not original.
- [x] **Decision recorded (September 20, 2026):** Felipe Bordeu generated and
  owns every file in `src/flowgraph/testdata/`; all are original FlowGraph Core
  material distributed under BSD-3-Clause.
- [x] **Evidence recorded (September 20, 2026):** Scanned the exact `uv.lock`
  resolution and fresh source/wheel artifacts. The lock contains 94 package
  records and the fresh `py3-none-any` wheel contains no bundled native
  binaries. Hashes, versions, metadata, and the stale-artifact warning are
  retained with the release record; license compatibility and native dependency
  review remain separate blockers.
- [x] **Evidence recorded (September 20, 2026):** Recovered upstream license
  identities for VTK, Muscat, meshio, Meshlane, SciPy, pandas, h5py/HDF5,
  Pillow, optional `pyplaid`, and optional `cosapp`. Sources and limitations are
  recorded with the release compliance evidence.
- [ ] Complete artifact-specific review of those components' native/transitive
  dependencies, bundled notices, generated code, and binary redistribution terms.
- [ ] Verify GPL/LGPL/AGPL obligations, Apache NOTICE requirements, attribution,
  patent, trademark, and binary redistribution conditions.
- [ ] Complete the license analysis; it must accurately cover the selected
  open-source license and exact release artifacts.
- [x] **Generated on September 20, 2026:** Established the compliance generator,
  notices, SPDX SBOM, native audit, preserved license texts, license review, and
  compliance tests as release evidence. Platform-specific native and
  bundled-notice review remains open.
- [x] **Decision recorded (September 20, 2026):** Use the Developer Certificate
  of Origin rather than a CLA. Contribution requirements are documented in
  `DCO.md` and `CONTRIBUTING.md`; commit sign-off remains to be enforced by the
  public repository settings.

## 2. Security, privacy, and code sanitization

- [ ] **Blocker** Enable and verify GitHub Secret Scanning and Push Protection for
  the current tree, reachable Git history, and future pushes. Review alerts and
  complete a manual review of releases and package artifacts.
- [ ] **Blocker** Revoke and rotate every credential exposed anywhere, including
  deleted history, CI logs, screenshots, examples, or documentation. Treat
  deleted secrets as compromised.
- [ ] **Blocker** If sensitive content is found in Git history, follow an approved
  history-rewrite/remediation process, force-push affected refs, invalidate old
  clones/artifacts, and document the response.
- [ ] Search for API keys, tokens, passwords, SSH keys, certificates, private
  URLs, internal hosts, cloud IDs, telemetry IDs, customer/project names,
  personal paths, test credentials, and confidential algorithms or data.
- [x] Added safe ignore rules for `.env`, local settings, credentials, signing keys,
  coverage, generated SBOMs, IDE state, build output, and temporary artifacts;
  no project configuration template currently contains secrets.
- [ ] Review workflow JSON, test fixtures, commit messages, comments, docs,
  screenshots, and architecture diagrams for personal, employer, customer, or
  other confidential information.
- [x] Confirmed repository-authored public documentation uses generic or
  repository-relative instructions.
- [x] Reviewed remote file access, user code, external tools, and browser/WASM
  integrations for command injection, path traversal, arbitrary code execution,
  SSRF, unsafe deserialization, unsafe archive extraction, and resource limits;
  remaining application-level network and resource policy is documented for
  embedding applications.
- [x] Documented threat model, security boundaries, trusted/untrusted workflow
  inputs, file/network access behavior, and user-code execution risks in
  `Architecture.md`, `docs/workflow-format.md`, and `SECURITY.md`.
- [x] Added a public vulnerability-reporting process and private security route
  documentation in `SECURITY.md`; repository settings still require owner action.
- [x] **Owner confirmation (September 20, 2026):** Enabled the GitHub dependency
  graph, Dependabot alerts, and Dependabot security updates; reviewed existing
  secret-scanning alerts.
- [ ] Enable and verify GitHub Secret Scanning, Push Protection, private
  vulnerability reporting, and CodeQL code scanning where available. The
  dependency graph and Dependabot controls above are complete; record the GitHub
  settings and successful scans as release evidence.
- [x] Added automated dependency vulnerability scanning to CI and defined triage,
  remediation, disclosure, and security-release procedures.
- [x] Confirmed that the core has no telemetry, analytics, or update checks;
  explicit network capabilities and embedding-application responsibilities are
  documented in `SECURITY.md`.

## 3. Git history, commits, and repository identity

- [x] **Decision recorded (September 20, 2026):** The final public repository URL
  is `https://github.com/FBW-Engineering-Solutions/FlowGraph.git`; local `origin`
  fetch and push URLs match it. Repository settings and public-launch review
  remain separate owner-controlled blockers.
- [ ] **Blocker** Review every reachable commit, branch, tag, release asset,
  workflow artifact, and Git LFS object for confidential/proprietary content,
  secrets, and third-party material.
- [ ] **Blocker** Review author and committer names/emails in public history;
  replace personal addresses with approved public identities if necessary.
- [ ] **Blocker** Choose the public-history strategy and record the decision:
  preserve the reviewed history, rewrite it, or create a fresh public history.
  An empty commit alone does not remove earlier private/development commits.
- [ ] **Blocker** Preserve a private backup of the current repository, including
  all branches, tags, and the current commit graph, before any history rewrite,
  orphan-branch creation, force push, or repository visibility change.
- [ ] **Blocker** Review the complete public snapshot independently of the private
  development history: tracked files, generated artifacts, ignored files that
  may be added accidentally, Git LFS objects, commit metadata, and reachable
  release assets.
- [ ] **Blocker** If private/development commits must not become public, create a
  clean orphan-based public `master` history from the reviewed working tree,
  add only approved files, create the first signed-off public commit, and verify
  that the new branch has no parent relationship to private development commits.
- [ ] If preserving history instead, remove or rewrite only the specifically
  identified confidential or misleading commits using an approved history-
  rewriting tool, then have an independent reviewer inspect the rewritten graph.
- [ ] **Blocker** Confirm the final remote before publishing: set both fetch and
  push URLs to `https://github.com/FBW-Engineering-Solutions/FlowGraph.git`,
  confirm the target repository and default branch are correct, and verify that
  no personal or private remote remains configured.
- [ ] **Blocker** Before making the repository public, inspect the exact commit
  that will be pushed, run the release security/license/artifact checks, and
  obtain independent approval for the source snapshot and history strategy.
- [ ] Push the clean public `master` branch only after the preceding checks pass;
  use a force push only when replacing an already-public branch is explicitly
  approved and the private backup is retained.
- [ ] After the first public push, verify GitHub visibility, default branch,
  branch protection, required checks, security settings, repository metadata,
  releases, tags, and reachable history from a clean external clone.
- [x] Verified on September 20, 2026 that `git ls-files` contains no virtual
  environments, caches, build output,
  validation directories, editor state, local documents, or accidental artifacts.
- [x] Added `.gitattributes` for text/binary classification, line endings, and
  archive exclusions. Added `.gitignore` rules for local environments,
  credentials, coverage, validation output, and temporary artifacts.
- [ ] Remove internal-only `memory-bank/`, `.clinerules/`, and agent-specific
  instructions from the public repository, or replace them with contributor-
  facing documentation. Confirm ignored files are untracked.
- [ ] Configure protected default branch rules: PRs, required checks, reviews,
  stale-review dismissal, signed commits if desired, linear history, and bypass
  policy.
- [ ] Create policies for labels, milestones, Projects, Discussions, wiki, issue
  moderation, and repository archival/transfer.
- [ ] Create an annotated, signed release tag for the first public release after
  final source and artifact review.

## 4. Documentation and public project presentation

- [x] **Blocker** Completed `README.md` for external users: purpose, capabilities,
  non-goals, installation, supported Python version, working quick start, CLI/API
  examples, docs, license, contributing, security, and changelog links.
- [x] Corrected stale README and changelog claims so they describe the headless
  core rather than private desktop UI functionality.
- [x] Removed private sibling-checkout requirements from public installation,
  documentation, and support guidance; optional integrations are documented
  without requiring sibling repositories.
- [ ] Verify each documented command works in a fresh clone on every supported
  operating system.
- [x] Added a structured `docs/` directory beginning with workflow JSON,
  compatibility behavior, and capability boundaries.
- [x] Reviewed `Architecture.md` for outdated claims, confidential information,
  ownership terminology, and external readability.
- [ ] Add examples using redistributable data, and execute them in CI.
- [ ] Add only meaningful badges (CI, package version, supported Python, license,
  docs, coverage), and ensure they reveal no private information.
- [ ] Add acknowledgments for contributors, upstream projects, sponsors, and
  funding where appropriate.
- [ ] Define branding/trademark/logo usage policy if trademarks are claimed.

## 5. Community, governance, and contributions

- [x] Added `/CONTRIBUTING.md` with `uv` setup, prerequisites,
  development workflow, test/lint/type-check commands, style, docs expectations,
  PR process, review expectations, and release-note process.
- [x] Added `/CODE_OF_CONDUCT.md`, an enforcement contact, and report-handling
  procedure.
- [x] Added `/SECURITY.md` with supported versions, private reporting route,
  response targets, disclosure policy, and PGP key if used.
- [x] Added and updated `SUPPORT.md` describing support channels, expected response levels,
  commercial boundaries, and how to ask usage questions.
- [x] Added issue templates for bugs, features, documentation, and a security-report
  redirect, plus a PR template for tests, docs, changelog, licensing, and
  compatibility checks.
- [x] Added `GOVERNANCE.md` defining current roles, decisions, escalation, and
  maintainer succession.
- [x] Implemented the chosen DCO process in contribution documentation; branch
  protection and sign-off enforcement remain repository-owner actions.
- [ ] Configure community moderation and automation only after reviewing privacy,
  permissions, and maintenance burden.

## 6. Package, release, and supply-chain readiness

- [ ] **Blocker** Complete public package metadata in `pyproject.toml`: license,
  classifiers, keywords, project URLs, source repository, docs, issue tracker,
  maintainers, contacts, and supported Python versions.
- [ ] **Blocker** Confirm the PyPI name is available/reserved and controlled by the
  intended organization with MFA, recovery contacts, and role separation.
- [ ] **Blocker** Build wheel and sdist from a clean clone; inspect contents;
  install each in fresh virtual environments; run imports, `flowgraph --help`,
  and representative workflows using installed artifacts only.
- [ ] Confirm `uv.lock` is intentionally committed/reproducible; refresh from the
  supported Python versions and review every lock change.
- [x] Added reproducible artifact validation evidence: metadata/build checks,
  distribution file inspection, license-like file hashes, SPDX SBOM, native audit,
  package import/test coverage, and CLI/workflow tests. A final release candidate
  still requires platform-specific artifact inspection.
- [x] Confirmed on September 20, 2026 that package data includes the required
  runtime fixtures, while wheel contents exclude tests, local files, secrets,
  compliance evidence, and unnecessarily large build artifacts. Test fixtures
  are intentionally shipped because packaged demo workflows depend on them.
- [x] Defined `pyproject.toml` as the version source of truth and `CHANGELOG.md`
  as the release-note source of truth; documented release steps in
  `packaging/README.md` and `RELEASE_POLICY.md`.
- [ ] Publish signed artifacts and/or provenance attestations. Use PyPI trusted
  publishing/OIDC and MFA instead of long-lived publishing tokens where possible.
- [x] Produce release checksums and SBOMs; the workflow now stores wheel, sdist,
  checksums, notices, SBOM, native audit, and preserved license texts as release
  evidence.
- [ ] Establish reproducible-build verification; consecutive local builds on
  September 20, 2026 produced different hashes. Known nondeterminism and the
  required future normalization work are documented in `packaging/README.md`.
- [x] Decided that optional `ml` and `cosapp` integrations are not part of the
  minimum support guarantee. Installation, dependency review, trusted-input
  requirements, and release testing expectations are documented in `README.md`
  and `SUPPORT_POLICY.md`.

## 7. CI/CD and release automation

- [ ] **Blocker** Review every workflow for permissions, secrets, untrusted PR
  behavior, artifact retention, log exposure, runner isolation, and supply-chain
  risk.
- [x] Removed the self-hosted/local/docker-container build and release runners;
  build and release jobs now use GitHub-hosted Ubuntu runners. Repository-owner
  review of public fork permissions remains required.
- [x] Pinned every GitHub Action currently used by the workflow to an immutable
  commit SHA with version comments; Dependabot is configured for update review.
- [x] Replaced mutable `version: latest` tool installation with the reviewed
  `uv` version `0.11.3`.
- [ ] Use minimum job-level permissions. Review `contents: write` in the release
  job and restrict release tags to trusted maintainers.
- [ ] Test supported Python versions and relevant operating systems, rather than
  only Python 3.13 on a local runner.
- [x] Added formatter, Ruff, pytest, package smoke-test, and dependency-audit
  gates to CI; GitHub-native security controls and compliance generation remain
  release responsibilities.
- [ ] Require passing checks before merge, and confirm checks work for external
  contributors and forks.
- [x] Updated release automation to use hosted runners and upload both wheel and
  sdist, checksums, notices, SBOM, native audit, and preserved license texts.
- [ ] Rehearse tag-to-release automation in a disposable repository or prerelease
  before public launch.
- [x] Defined retention inputs, rollback, yank/revoke, incident response, and
  credential-rotation procedures in `RELEASE_POLICY.md` and `SECURITY.md`.

## 8. Code quality, testing, and API readiness

- [ ] **Blocker** Run from a clean clone: `uv sync --locked --extra dev`,
  `uv run ruff format --check .`, `uv run ruff check .`, `uvx ty check src` where
  applicable, and `uv run pytest`.
- [ ] Ty type checking was run with the current command `uvx ty check src` on
  September 20, 2026 and reported 24 existing diagnostics, including third-party
  Muscat/Pyodide stub resolution and pre-existing adapter typing issues. Resolve
  or explicitly scope these before claiming a clean type-checking gate.
- [ ] Resolve or document every failure, skip, flaky test, platform limitation,
  optional-dependency condition, and resource-heavy test.
- [ ] Add coverage reporting and a reviewed threshold for workflow validation,
  persistence, execution, CLI, and security-boundary code.
- [ ] Audit public APIs, exports, docstrings, errors, input validation, and
  exception semantics. Remove or clearly label experimental/internal APIs.
- [x] Documented workflow JSON format, versioning, compatibility, legacy migration,
  and unknown-node/parameter behavior in `docs/workflow-format.md`.
- [ ] Test malformed/corrupt workflow files, invalid paths, cyclic graphs,
  unavailable optional dependencies, failure recovery, and untrusted input.
- [ ] Add regression tests for public bugs and ensure examples run without sibling
  repositories or local machine configuration.
- [ ] Review performance/memory behavior with realistic mesh/image inputs; state
  supported limits and known bottlenecks.
- [ ] Run static analysis and dependency audits; triage findings with rationale
  instead of blanket suppression.

## 9. Final publication and post-launch operations

- [ ] Freeze a release-candidate commit and repeat secret, license, privacy, and
  artifact scans against that exact SHA.
- [ ] Have an independent reviewer approve legal/IP, security/privacy, source,
  artifact, and release checks.
- [ ] Create release notes from verified changes, known limitations, upgrades,
  breaking changes, acknowledgments, checksums, and support route.
- [ ] Verify public repository description, topics, website, social preview,
  default branch, visibility, license selector, issue settings, Discussions, and
  security settings.
- [ ] Publish a prerelease if practical; install it through public channels from a
  clean machine/account and follow the README exactly.
- [ ] Publish signed tag, GitHub release, and package artifacts only after all
  blockers pass. Verify package pages and source archives immediately.
- [ ] Monitor issues, CI, package publication, dependency alerts, and security
  reports after launch; assign initial triage ownership.
- [ ] Archive release inputs: commit SHA, tag signature, build logs, checksums,
  SBOM, lockfile hash, license report, approvers, and publication time.
- [ ] Schedule recurring dependency updates, license rescans, secret scans,
  supported-version reviews, documentation maintenance, and release rehearsals.

## Final go/no-go record

- [ ] All **Blocker** items are complete or have a documented, approved exception.
- [ ] An external contributor can clone, build, test, and use the project without
  access to local paths, sibling repositories, private infrastructure, or
  unpublished context.
- [ ] Release candidate commit SHA: `____________________`
- [ ] License/IP approval by and date: `____________________`
- [ ] Security/privacy approval by and date: `____________________`
- [ ] Release approval by and date: `____________________`


Confirm the public project name, PyPI distribution name
  (`flowgraph`), Python namespace (`flowgraph`), organization, logo, domain, and
  social handles are available and do not infringe another party's trademarks.