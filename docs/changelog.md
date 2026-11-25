New in version 0.1.10:
**********************
**********************

FlowGraph Core 0.1.10 is an alpha release focused on time-dependent mesh I/O
and workspace path overrides. Desktop and Web clients are released separately.

Changes and fixes:

- Fix Convert Mesh File Format when exporting a time-dependent mesh to a
  single-snapshot writer such as MeshIO. The selected snapshot is now written;
  All falls back to the last snapshot for these writers.

- Convert Mesh File Format writes a single static mesh when the reader reports
  no time steps, instead of failing with the default Last time step setting.

- For connected Workspace File and Workspace Folder inputs, skip filesystem validation
  so new writer destinations are allowed, even when files or directories do not
  exist. Retain validation for selector-only paths and legacy absolute references.

New functionalities and improvements:

- Extract Vector Value also outputs the integer index used, preserving negative indices.

- Add a connectable integer time-step index to Read Mesh (Muscat), defaulting to
  `-1` (last snapshot). The reader outputs only the selected mesh, not a series.
  Add an Available Time Steps output that can be used without loading any mesh.
  It defaults to `[0.0]` when no time steps are reported.

- Expose all Convert Mesh File Format parameters as connectable inputs while
  retaining their defaults and controls. Return the converted filename as the
  declared `FilePath` type so it can be passed to downstream nodes.

- Expose Workspace Folder's optional folder Text/Path input for branch-local
  overrides, preserving its saved dropdown fallback.

- Add optional workspace-path and relative-file inputs to Workspace File. Connected
  values override runtime/selector fallbacks without replacing the saved selection.

- Add `POST /api/v1/files/directories` to the authenticated local server API.
  It creates an empty workspace directory whose parent already exists.

Migration and limitations:

- To select a snapshot in Read Mesh (Muscat), use `0` for the first or `-1`
  for the last. To process multiple snapshots, use Available Time Steps to
  drive repeated reads by index; the Mesh output contains one snapshot per run.
- Connected workspace inputs can point to paths that do not exist. The path
  nodes do not create those paths; the downstream reader or writer handles them.

New in version 0.1.9:
**********************
**********************

FlowGraph Core 0.1.9 remains an alpha release, with breaking workflow changes.
This release focuses on portable workspaces, trusted native plugins, execution
diagnostics and recovery, ImageJ integration, and mesh/image workflow improvements.
Review the migration guidance below before opening existing workflows. Desktop
and Web clients have separate validation and distribution procedures.

Changes and fixes:

- Use a bounded staged close for ParaView HTTP connections so rejected uploads
  can receive their error response without a Windows connection-reset race.
  Origin authorization remains exact-match and rejected data is never accepted.

- Fix Windows plugin path diagnostics, reject rooted Workspace Folder selections,
  and keep execution failures reportable when temporary-file cleanup fails.
  Preserve CLI string output formatting in cross-platform tests.

- Fix Transfer Fields' default to use the Muscat value `Interp/Clamp`, not its
  display label; retain Nearest point and test all five transfer choices.

- Defer five nested-selector regression cases that fail with Muscat 2.6.0 to
  branch `tests/muscat-next` for integration with a future version; retain the
  selector tests supported by the current dependency.

- Add ROI/LOI Negate Y, off by default, to negate output Y coordinates only.

- Rename display nodes to Show Mesh and Show Table without changing saved IDs.

- Use 2D Vector (VEC2D) for ROI/LOI point outputs, preserving combined Any outputs.

- Add ROI (`image-roi`) with optional image input, editable integer corners and
  immutable tuple output; web selection uses original pixel coordinates.

- Add LOI (`image-loi`) with equivalent line selection, editable integer endpoints
  and immutable tuple output preserving endpoint order.

- Expose separate `point1` and `point2` 2D Vector outputs as two-element float lists
  on ROI and LOI while keeping their combined immutable tuple outputs.

- Require Muscat 2.6.0 or newer for compatibility with the quadratic-to-linear API.
- Add the base dependency `packaging>=24` and the optional `server` extra
  (`uv>=0.6`) for native workspace package installation.
- Lock Muscat from PyPI and verify release configuration does not depend on a
  sibling editable checkout.
- Use Muscat 2.6's `linearizeMiddlePoints` parameter in both quadratic-to-linear
  nodes without a legacy alias.
- Bump the core package, runtime and lockfile version to 0.1.9; synchronize
  Desktop's core dependency without changing Desktop's own version.

New functionalities and improvements:

- Add Workspace Folder (`workspace-folder`) with a workspace-relative Text
  selection and Path (`pathlib.Path`) output. Read Directory Files now accepts
  Path directly; Path can also convert to FilePath for file consumers.
- Replace Select uploaded file with Workspace File (`workspace-file`). Resolve
  relative selections against the host-configured workspace, validate containment
  and file existence, and invalidate caches when the workspace root changes.
  Existing absolute file references remain external references.
- Add `flowgraph run --verbose` / `-v` and extend server verbose mode with live
  execution diagnostics, worker stdout/stderr and bounded node output summaries.
  Normal output stays unchanged; verbose logs may contain sensitive data.
- Expose node progress, elapsed time and cursor-based live node results in server
  job polling. Add authenticated execution-state recovery for submitted workflows
  and session options; recovery is in-memory, not persistent across server restarts.
- Make native execution timeouts advisory: retain workers and late results until
  explicit cancellation or service shutdown, and expose timeout state to clients.
- Add trusted Python-file plugins through repeatable `--plugin FILE.py` options
  for CLI and server startup, plus explicit registries for Python hosts. Plugins
  export `AVAILABLE_NODES`; duplicate definition IDs are rejected.
- Add opt-in native package check/install APIs with isolated workspace storage
  and verified wheels, and WASM package checks with confirmed session-only
  installation. Package installation is not enabled by default.
- Add `flowgraph serve --host` and `--public-url` for HTTPS reverse-proxy hosting,
  retaining bearer authentication, Host/Origin validation and loopback defaults.
- Add ImageJ To Pillow (`imagej-to-pillow`), ImagePlus script input/output support,
  script parameter metadata handling and a bundled Gaussian Blur example. Report
  PyImageJ, CoSApp and Plaid versions in server runtime metadata.
- Improve Compute Skin's boundary extraction and read-only metadata retention;
  skip boundary extraction when its output is unused. Remove unused preview nodes
  before 3D-view serialization without modifying the source mesh.
- Use Muscat's NodeFilter directly for nested nodal selection. Keep packaging
  inventory checks compatible with unversioned editable dependencies.

Breaking changes and workflow migration:

- No legacy aliases are provided for the renamed node definition IDs. In saved
  workflow JSON, change `definition_id` from `select-server-file` to
  `workspace-file`. For workflows saved during development with `workspace`,
  change it to `workspace-folder`. Apply these changes in nested workflows too;
  do not rename node instance IDs or edge endpoints merely to match definitions.
  Workspace Folder is new since 0.1.8; its root selection defaults to `.`.
- In both quadratic-to-linear nodes, rename the saved parameter key
  `linearizedMiddlePoints` to `linearizeMiddlePoints`, preserving its value.
  The old parameter name has no alias. Muscat 2.6.0 or newer is required.
- Compute Skin (`extract-skin`) retains the full mesh on `mesh` and exposes the
  boundary-only mesh on `skin_mesh`. Reconnect consumers needing only the boundary
  to `skin_mesh` and review the configurable `Skin_Name`.
- Rebuild or update Desktop/Web clients and their catalogs against the matching
  Core version before using these changed node definitions and port types.
- Read Directory Files now consumes Path (`pathlib.Path`) instead of FilePath;
  review custom Python callers and connections to that input.
- Native execution timeouts are advisory, not automatic termination. Hosts that
  require a hard stop must explicitly cancel the execution; otherwise the worker
  can continue and deliver late results.

Known limitations and operational notes:

- Muscat 2.6.0 has known nested-selector failures. Five unsupported regression
  cases are deferred; this release does not claim to fix those dependency issues.
- Transfer Fields' Nearest point (`Nearest/Nearest`) mode can fail for P0 element
  fields with Muscat 2.6.0. The four interpolation modes remain covered for element
  fields; nearest-point nodal transfer is covered separately.
- Python-file plugins and code-execution nodes run trusted arbitrary code, not in
  a security sandbox. The local server must be configured and exposed only to
  trusted users; reverse-proxy support does not make untrusted workflows safe.
- Package installation is opt-in. Native package storage is workspace-local;
  browser package installation is session-only and does not persist after reload.
- Execution recovery is in-memory and does not survive server restart. Verbose
  output can include paths, node values, and other sensitive information.
- ImageJ/Fiji and other optional integrations need their external runtimes and
  dependencies. Core wheel/sdist smoke tests do not certify every optional backend
  or the separate Desktop and Web applications.
- Python 3.11–3.14 are the CI target versions on Ubuntu, Windows, and macOS;
  platform support for this release depends on the corresponding candidate jobs
  passing. A pure-Python Core wheel still requires compatible native dependency
  wheels; `requires-python >=3.11` alone is not a promise for newer interpreters.
- Release preparation documentation now distinguishes automated dependency and
  artifact checks from manual redistribution review; no generated SBOM, native
  audit, or complete license bundle is claimed by the current workflow.

New in version 0.1.8:
**********************
**********************

Planned first MVP baseline, not a publication announcement or a stable API
commitment. The `0.1.x` series remains alpha.

Improvement:

- Strip location/capture metadata from the ColorCardboard fixture while preserving
  decoded pixels, and make ParaView gateway examples independent of personal paths.
  This does not replace previously published packages or rewrite history.

- Retain CI packages for 30 days and document durable manual release-evidence
  capture, publication-hash comparisons, and independent backup verification.

- Make the Core CI gate and its regression tests portable with Python instead
  of invoking the WSL Bash launcher on Windows.

- Add the stable Core CI aggregate gate, fail-closed prerequisite tests, and
  PR publication-permission regressions. Document single-maintainer branch/tag
  policy and manual DCO review; remote protection rollout is still pending.

- Remediate four dependency advisories by locking setuptools 84.1.0 and urllib3
  2.8.0, and require setuptools 84.1.0 or newer for isolated package builds.

- Target CI dependency audits at exact installed project-environment pins, with
  logged inventory, explicit local-project exclusion, and regression coverage.

- Remove local-machine build notes from package configuration and use ignored,
  repository-relative rehearsal output with `uv run python` artifact checks.

- Refresh security, maintainer, support, and release guidance for ongoing Core
  alpha operations; distinguish release checks from the maintenance backlog and
  keep platform/client support conditional on relevant validation.

- Establish 0.1.8 as the planned first MVP baseline and remove obsolete historical
  release-audit references. Release-version validation remains required.

- Update installation requirements, pure-Python packaging, runtime extras, and
  persistent/source/temporary commands; test the documented CLI examples.

- Correct third-party notices for BSD-3-Clause Core with a dated dependency and
  license-evidence overview, explicit review limits, and inventory regression tests.

- Add the documentation URL to package metadata and record passing CI evidence
  for the existing Python 3.11–3.14 classifiers, with metadata consistency tests.

Api Change:
- Remove the Conda packaging recipe and its release validation. Supported release
  artifacts remain the Python wheel and source distribution on GitHub and PyPI.
- Move meshio, Meshlane, pandas, h5py, Pillow, and openpyxl to the optional
  `io` extra. Install `flowgraph[io]` (or use `uv sync --extra io` in a source
  checkout) for workflows using these libraries. Version constraints are unchanged.

New in version 0.1.7:
**********************
**********************

Api Change:
- Replace `flowgraph.application.wasm_execution` with the transport-independent
  `flowgraph.application.workflow_execution` module. No compatibility alias is
  retained. `execute_workflow_json()` and its response format are unchanged;
  browser workers must update their imports and rebuild/stage the core wheel.
- Composite nodes now store string-keyed `subworkflows`; definition factories use
  `subworkflows_factory`. The single-child `subworkflow` property remains as a
  compatibility view of the `"default"` child. Workflow JSON is version 3;
  existing version 1/2 workflows remain readable and migrate on export.

New functionalities:
- Include token and actual bound port in hosted `Open editor` launch fragments
  for one-click local backend selection; native editor links remain unchanged.
- Always print an `Open editor` address at server startup pointing to the
  independently hosted allowed client origin.
- Default `flowgraph serve` to the public editor origin `https://flowgraph-web.fbw-es.com`
  and port 8765. Explicit repeatable `--allow-origin` values replace the default;
  loopback binding and bearer authentication remain unchanged.
- Permit explicitly allowed HTTP loopback editor origins for local development,
  including the serial editor at `http://127.0.0.1:8082`; public origins still require HTTPS.
- Add opt-in `serve --allow-origin HTTPS_ORIGIN` for public editor connections to
  loopback Python: restricted CORS/preflight support with unchanged bearer and
  Host validation, no wildcard origins or network exposure.
- Add the experimental `flowgraph serve --workspace ...` loopback-only HTTP API,
  with generated bearer authentication, Host/Origin checks, runtime/catalog
  metadata, workspace file operations, and one cancellable native execution job
  at a time. Jobs use the shared execution boundary in fresh subprocesses.
  Includes request/result limits, execution timeout, shutdown cleanup and real
  HTTP integration tests. API only; no editor hosting or frontend adapter yet.
- Conditional Workflow executes only its selected `"true"` or `"false"` child,
  including branch-local producers, and exposes matching published branch
  outputs as an implicit join. Its boolean condition accepts a saved value or
  connected input. Named children are included in CLI inspection, code warnings,
  default resolution, and catalog metadata.

Corrections:
-

Improvement:
- CI source and wheel/sdist tests now include Python 3.12 and 3.14 alongside
  Python 3.11 and 3.13 on Ubuntu, Windows, and macOS.

New in version 0.1.6:
**********************
**********************

Api Change:
-

New functionalities:
- `flowgraph run` resolves omitted published inputs from compatible saved
  downstream parameter values, including nested workflow inputs and directly
  exported parameters. Each fallback emits a warning to stderr with the input,
  chosen value, and source parameter. Explicit inputs take precedence; missing
  defaults and conflicting downstream values still require explicit inputs.

Corrections:
- Release validation now compares tags, source version declarations, artifact
  filenames, and internal wheel/sdist metadata before GitHub or PyPI publication.

Improvement:
- Branch and pull-request CI now rehearses packaging without publishing: wheel
  and sdist installs are tested independently across the OS/Python matrix,
  including packaged resources and installed CLI workflow execution. Manual
  dispatch never publishes; actual version-tag pushes remain the release trigger.


New in version 0.1.5:
**********************
**********************

The `0.1.x` series is alpha. APIs, workflow behavior, and compatibility
guarantees may change before the `1.0.0` stability milestone.

Api Change:
-

New functionalities:
-

Corrections:
-

Improvement:
-
