# FlowGraph Core Brand and Name Review

**Review date:** September 20, 2026  
**Scope:** Public FlowGraph Core release  
**Status:** Open; not trademark clearance or legal advice

## Current identifiers

| Identifier | Current value | Preliminary result |
| --- | --- | --- |
| Project name | FlowGraph Core | **Open:** adjacent software uses and trademark risk require legal review |
| PyPI distribution | `flowgraph` | Existing project controlled by the `FelipeBordeu` PyPI account; audit existing releases before publishing the open-source release |
| Python namespace | `flowgraph` | Used by this source tree and existing package releases; preserve only after final naming decision |
| GitHub organization | `FBW-Engineering-Solutions` | Public organization exists; owner/recovery configuration cannot be verified from public data |
| GitHub repository | `https://github.com/FBW-Engineering-Solutions/FlowGraph.git` | Final repository URL supplied by the project owner and confirmed as the current local `origin`; repository settings and public-launch readiness remain open |
| Logo | None found in this repository | No asset is currently available for a visual-conflict review |
| Domain | None selected | Availability and ownership have not been checked |
| Social handles | None selected | Availability and ownership have not been checked |

## Evidence and findings

### PyPI

The normalized package name `flowgraph` is already published on PyPI and the
public project record identifies `FelipeBordeu` as its owner. Before a public
open-source release, compare the currently published releases with this source
tree, decide whether old releases should be yanked or superseded, and ensure
the new metadata and license are correct.

### GitHub

The project owner confirmed on September 20, 2026 that the final repository URL
is `https://github.com/FBW-Engineering-Solutions/FlowGraph.git`. The local Git
`origin` fetch and push URLs match this value. This confirms repository identity,
but does not verify GitHub settings, branch protection, security features,
maintainer recovery, or public-launch readiness.

### Name collisions

Public search found multiple software products or libraries using `FlowGraph`,
`Flowgraph`, or closely related names for graph editors, workflow composition,
AI workflow automation, visual AI pipelines, diagramming, and node-based
software. This creates a meaningful likelihood of confusion in adjacent
software markets.

A U.S. FLOWGRAPH trademark application was also identified for software-as-a-
service and data-analytics-related services. Its scope and status must be
reviewed by qualified trademark counsel before treating the name as cleared.

## Required actions before closing this release-checklist item

- [x] **Decision recorded (September 20, 2026):** The final public repository
      URL is `https://github.com/FBW-Engineering-Solutions/FlowGraph.git`; the
      local Git `origin` fetch and push URLs match it.
- [ ] Audit existing PyPI `flowgraph` releases and decide whether to yank,
      replace, or supersede them.
- [ ] Perform a professional trademark clearance search for `FLOWGRAPH`,
      `FlowGraph`, `Flowgraph`, `Flow Graph`, and relevant variants in every
      jurisdiction where the project will be distributed, marketed, or supported.
- [ ] Review software, SaaS, workflow automation, data processing, engineering,
      AI, and developer-tool trademark classes and related goods/services.
- [ ] Decide whether the name is legally acceptable or whether a more distinctive
      name is required before publication.
- [ ] Select and register the intended domain name(s) and social handles only
      after the naming decision; record account ownership and recovery contacts.
- [ ] Create or commission an original logo only after the name decision and
      record its copyright/trademark ownership.
- [ ] Update GitHub settings and complete the remaining public-launch review using
      the confirmed repository URL. Package metadata and release documentation
      now use `https://github.com/FBW-Engineering-Solutions/FlowGraph`.

## Conclusion

The package name is technically occupied by the project owner, and the GitHub
organization is available for project administration. These facts do not prove
trademark clearance or guarantee ownership of the desired repository, domain,
or social handles. Keep the release blocker open until the actions above are
completed and recorded.