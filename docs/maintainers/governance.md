# Governance

FlowGraph Core is maintained by Felipe Bordeu, who serves as the
maintainer, release manager, and security contact. The project is
pre-1.0 and decisions prioritize correctness, reproducibility, security,
licensing clarity, and preservation of the headless core boundary.

## Decision process

Technical changes should be proposed in an issue or pull request with context,
alternatives, tests, compatibility effects, and documentation impact. The
maintainer makes the final decision after considering review feedback and the
release policy. Security reports and personal-conduct reports follow their
private procedures and are not decided in public threads.

## Maintainer responsibilities

The maintainer is responsible for reviewing contributions, protecting release
credentials, maintaining the supported-version policy, coordinating security
fixes, preserving provenance and license notices, and publishing releases only
after applicable release checks pass and relevant unresolved risks have been
reviewed and recorded. Optional improvements are not automatic release blockers.

## Contribution and repository protections

The single-maintainer policy requires pull requests into `master`, resolved
review conversations, and passing Core CI, but zero mandatory approvals so the
maintainer can merge their own work. No routine administrator bypass is intended.
Keep deletion and force-push protection. DCO sign-offs remain mandatory for each
contribution commit; the maintainer checks them manually before merging. There
is no automated DCO check, and cryptographic commit signatures are not DCO sign-offs.

Core CI is the stable aggregate of source tests (including lint and dependency
audit), package building, and wheel/sdist installation tests. Failed, cancelled,
or skipped prerequisites must fail this gate. Configure `Core CI` as a required
check with GitHub Actions as its expected source, requiring the branch to be
up to date before merging. Do not require tag-only publication jobs on PRs.

**Rollout pending:** these are the approved target settings, not a claim that
remote enforcement is active. Push the workflow changes and obtain a successful
hosted Core CI run before activating required checks. Then verify the effective
rules for `master`: PR required, zero approvals, conversations resolved, Core CI
required from GitHub Actions, up-to-date branch required, no deletion/force push,
and no routine bypass. Read back both the rules and their branch targeting.

Use separate rulesets for `v*` release-tag creation and immutability. Restrict
creation to trusted repository administrators; the creation-only ruleset allows
that role to bypass. Separately restrict tag updates and deletion with no routine
bypass, so creation permission does not permit moving existing release tags.
Verify both tag rulesets and their targeting after activation. Tag restrictions
alone do not establish that a commit was reviewed or passed CI.

External contributions run through `pull_request`, not `pull_request_target`.
The workflow defaults to read-only contents access; release writes and publishing
OIDC permissions are confined to tag-push jobs. Never grant fork PRs release
credentials. After rollout, rehearse an external fork PR: check any required
workflow approval, confirm Core CI runs, and verify publication jobs are skipped
and no write/OIDC job is executed. Local regression tests do not replace this
hosted rehearsal. PyPI environment and trusted-publisher restrictions are a
separate control and must not be inferred from branch/tag protection.

## Succession and continuity

FlowGraph is maintained by one developer. The current policy does not require
an independent backup owner. The maintainer is responsible for account
security, MFA, recovery methods, private repository backups, and release-record
retention. Any future change in maintainership or repository ownership must be
recorded in a dated project decision and reflected in the public support and
security documents.