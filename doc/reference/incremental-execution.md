# Incremental execution

`WorkflowExecutor.run` remains stateless. For incremental Python execution use:

```python
from flowgraph.application.workflow_session import WorkflowSession

session = WorkflowSession(registry)
result = session.run(graph, targets={"target-node"})
result = session.run(graph)  # Reuse valid results; execute other required nodes.
result = session.run(graph, targets={"target-node"}, force={"target-node"})
result = session.run(graph, from_scratch=True)
session.clear()  # Does not delete user files.
```

Serialize calls to a session. Selected targets automatically include upstream
dependencies. Forced nodes invalidate downstream results without executing nodes
outside the requested scope. `execution_order` contains actual successful node
executions; `session.metadata` separately reports reused, failed, blocked,
invalidated and evicted nodes. Returned inputs/outputs include available valid
results, including reused results. Do not mutate returned runtime objects.

## Correctness contract

### Scoped debugging runs

`WorkflowSession.run` accepts `upstream="normal"` (default), `"missing"`, or
`"none"`, and `missing_only=False`. Normal mode applies node policies throughout
the target dependency closure. Missing mode reuses valid upstream results even
from `always`/`composite` nodes, executing dependencies only when results are
missing or outdated. None mode executes no nodes outside `targets` and blocks
targets with unavailable upstream results. Selected nodes can be forced with
`force=targets`; their dependents become outdated. `missing_only=True` reuses all
valid requested results regardless of policy. Full-workflow missing requests
already include every node, so no-upstream does not shrink that scope.

All modes reconcile configuration and validate external dependencies throughout
the dependency closure before supplying stored inputs. There is no stale-output
override. The JSON execution options expose the same names; native backends
advertise `scopedExecution: 1` to prevent old servers ignoring these constraints.

All nodes, including User Functions and nested workflows, **must not modify
inputs**. This includes nested containers, NumPy arrays, mesh fields and storage
reachable through views. Inputs may be shared by sibling branches and retained
between runs. Transformations must produce new output data, copying only storage
that needs modification; unchanged data may be shared through read-only views.

Input mutation is a node implementation bug, not a supported execution policy.
The executor does not detect, sandbox or roll back such violations. In-place
mutation can corrupt sibling results and cached data even in stateless execution.
The default User Function body includes this warning; existing authored code is
not rewritten.

Definitions default to `pure`: deterministic computations reuse unchanged inputs
and parameters. `cache_policy=None` means omitted and is resolved at definition
construction; catalogs expose the resolved policy, never `None`.

- Declared file parameters or input ports (`filename` / `ServerFile`) infer
  `external` and a timestamp-plus-content resolver if no policy is specified.
- A supplied `cache_dependencies(inputs, parameters)` resolver also infers
  `external`, even without typed file fields.
- Explicit policies always win. Path-only selectors/manipulators **must explicitly
  declare `cache_policy="pure"`**; file contents do not affect their output.
- Writers, downloads, arbitrary Python/Groovy/CoSApp code and stateful operations
  explicitly declare `always`. Nested workflow wrappers declare `composite`.
- Ordinary strings are not guessed to be files, even when named `path`.
  String-only readers must declare a dependency resolver explicitly.

Automatic resolvers honor connected inputs over parameter defaults, fingerprint
all declared file fields (with arbitrary names), and carry explicit `FilePath`
companions. The standard single `path` field uses `single_file_dependency`.
Hidden companion files are not discovered automatically. Readers assume that
**every unlisted companion change updates the principal file modification time**.
Muscat, MeshIO and MeshLane therefore infer `external` from their file parameter.
If a producer cannot honor this contract, use a custom resolver listing its
companions or explicitly select `always`. Explicitly listed `FilePath` companions
are checked independently. Plaid disk-backed access and directory listings remain
explicitly `always`.

Dependency checks compare resolved path, file identity, size and nanosecond
modification/change timestamps first. Any metadata change invalidates immediately,
even if content is identical; after execution a SHA-256 digest establishes the new
baseline. Unchanged metadata still requires streaming SHA-256 verification to
detect content edits with preserved timestamps. Thus unchanged-file cache checks
still read file contents. Access time is ignored. Missing/unsupported/unreadable paths
never produce a cache hit. Dependencies are checked before and after execution;
changes observed during execution prevent retention. Explicit non-external policies
do not invoke dependency resolvers.

When a declared file input or parameter points to a directory, its dependency
snapshot recursively includes files in all subfolders, recording each file's
relative path, nanosecond modification timestamp and size. Added, removed,
renamed or metadata-changed files invalidate reuse. Directory file contents are
not hashed: content edits preserving both size and modification time are not
detected. Empty directories are supported; empty subfolder changes alone do not
invalidate results. Tracking is limited to **1,000 files per directory input**,
including all subfolders. On encountering a 1,001st file, scanning stops and the
dependency becomes uncacheable: execution still proceeds, but its result is not
retained for reuse. Unreadable trees, nested symlinks (including directory cycles)
and special files also prevent caching rather than silently omit dependencies.
The existing explicitly `always` directory-listing node keeps its policy.

Cache policies govern reuse, external dependencies and side effects, never input
ownership. There is no per-node mutation flag or mutation-based alias invalidation.

Signatures include definition identity/revision, effective parameters, port
contracts, edge mappings/conversions, connected outputs, upstream generations,
injected inputs, execution capabilities and nested graph semantics. Positions do
not invalidate computation. Connected parameter values are execution-derived and
are tracked through their supplying edge/input rather than duplicated settings.
Session runs restore authored parameter mappings after each node executes, so
disconnecting a parameter port restores the authored value rather than the last
execution-derived value. The legacy stateless executor behavior is unchanged.
Unsupported opaque direct Python inputs deliberately miss cache; large arrays and
meshes are not hashed implicitly. Definition changes should bump `cache_revision`.

Composite wrappers execute each request so active child actions are never skipped;
child sessions reuse safe computations independently. Conditional alternatives and
batch iteration indices use isolated namespaces. Opaque child inputs conservatively
miss cache. Out-of-scope branches retain their last-completed results regardless
of cache policy, unless configuration or upstream execution invalidates
them. They are listed in `outside_scope`, not counted as executed or reused in
the selected request. External state is not polled for untouched branches;
external dependencies and always/composite execution policies are rechecked when
those nodes next enter the requested scope. Retaining a preview does not certify
that external state has remained unchanged since that branch last ran.

## JSON and transports

`execute_workflow_json(workflow_json)` stays stateless. Pass an options mapping
with `session_id`, optional `targets`/`force` arrays and `from_scratch` boolean to
enable sessions. Responses add `cache` metadata, version 1 and a runtime epoch.
Use `clear_execution_session(session_id)` to dispose an in-process session.

Native `POST /api/v1/executions` accepts `options` beside `workflow`. Runtime
capabilities advertise `incrementalExecution: 1`. Session execution uses a
persistent subprocess, while legacy requests retain per-job subprocess isolation.
Authenticated `POST /api/v1/execution-sessions/dispose` accepts `session_id`.
Cancellation/timeouts kill the affected process; recovery starts cold. Sessions
retain interpreter state and are not a security boundary for arbitrary user code.

## Lifetime and limits

No disk-persisted or cross-restart cache is provided. In-process JSON execution
retains at most eight sessions, each with 256 entries and 32 child-session slots
per nesting level. Native execution retains at most four session workers and
expires idle workers lazily after 30 minutes when another execution is submitted.
LRU eviction causes recomputation, not invalid results. Limits count entries, not
bytes: a single mesh or nested workflow can be large. There is no hard aggregate
memory budget yet. Clear cache to release retained runtime objects.

Preview serialization is currently regenerated from valid retained inputs rather
than independently cached. Graph edits hide obsolete web previews conservatively;
the backend still retains independent valid computational entries.