New in Next :
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

Source version (not a publication announcement). As of October 22, 2026,
PyPI's latest version is `0.1.2`; see `release-reconciliation.md` for the
historical tag/asset mismatches and correction policy.
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
