New in version 0.1.9:
**********************
**********************

- Use 2D Vector (VEC2D) for ROI/LOI point outputs, preserving combined Any outputs.

- Add ROI (`image-roi`) with optional image input, editable integer corners and
  immutable tuple output; web selection uses original pixel coordinates.

- Add LOI (`image-loi`) with equivalent line selection, editable integer endpoints
  and immutable tuple output preserving endpoint order.

- Expose separate `point1` and `point2` tuple outputs on ROI and LOI while keeping
  their combined selection outputs.

- Require Muscat 2.6.0 or newer for compatibility with the quadratic-to-linear API.
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
