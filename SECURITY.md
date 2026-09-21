# Security Policy

## Reporting a vulnerability

Do not report suspected vulnerabilities in public GitHub issues.

Use GitHub private vulnerability reporting for this repository. Before the
repository is made public, the repository owner must enable private vulnerability
reporting in the repository security settings and verify that reports reach
Felipe Bordeu.

Include a clear description of the issue, affected FlowGraph version, impact,
reproduction steps or proof of concept, and any suggested mitigation. Do not
include secrets, customer data, or other sensitive material unless it is strictly
necessary to demonstrate the issue.

If private vulnerability reporting is unavailable, contact the initial security
contact through the private contact mechanism configured for the public
repository. Do not use a public issue, pull request, or package metadata field
for sensitive reports.

## Initial security contact and handling

Felipe Bordeu is the initial security contact and is responsible for triage and
release coordination. Reports are acknowledged when practical, normally within
seven calendar days, but no guaranteed response or remediation timeframe is
offered while the project has a single initial maintainer.

The initial process is:

1. Acknowledge and assess the report privately.
2. Determine affected versions and practical mitigation.
3. Prepare and test a fix or documented workaround.
4. Coordinate disclosure after a fix or mitigation is available.
5. Publish a security advisory and release notes when appropriate.

## Supported versions

The latest public FlowGraph Core release is the primary supported version for
security fixes. The immediately preceding release may receive a fix when the
change is low-risk and backporting is practical. Unsupported or unreleased
working-tree builds are not security-support commitments.

The core contains no telemetry, analytics, update checker, or background network
service. Network access occurs only through explicit workflow capabilities such
as the remote-download adapter or dependency/package tooling. Applications
embedding FlowGraph are responsible for obtaining any required user consent and
applying their own network policy.

## Disclosure and release process

The maintainer will reproduce and assess a report privately, identify affected
versions, prepare and test a mitigation, and coordinate disclosure after a fix
or workaround is available. A security release should include affected versions,
severity rationale, upgrade guidance, and required configuration changes without
publishing exploit details that would materially increase risk.

Security fixes must be checked for release-note, changelog, dependency, SBOM,
and artifact impacts before publication. Rotate any credential that may have
been exposed, including credentials found in deleted history or CI logs.

## Continuity and recovery

FlowGraph is initially maintained by one developer. An independent backup owner
is not required for the initial alpha release. The maintainer must protect the
GitHub and PyPI accounts with MFA, configure account recovery, retain a private
repository backup, and preserve release artifacts, checksums, and publication
records. A second maintainer or backup owner can be added later as the project
grows.