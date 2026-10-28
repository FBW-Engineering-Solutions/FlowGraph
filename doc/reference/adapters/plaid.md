---
id: reference.adapters.plaid
title: Plaid Nodes
section: Reference
order: 22
description: Optional nodes for loading and inspecting Plaid datasets.
---

# Plaid nodes

The **External Tools → Plaid** group and its icons are available for workflow
authoring even when the optional `pyplaid` package is not installed. Executing
nodes that load or process Plaid data requires the package providing
`plaid.storage.reader`; FlowGraph reports that requirement when such a node runs.

| Node (ID) | Inputs/outputs | Parameters/defaults |
| --- | --- | --- |
| **Load Plaid Dataset** (`load-plaid-dataset`) | Outputs `dataset: Plaid dataset`, `infos: Plaid info`, `splits: List Text` | `path=""` (optional input port) |
| **Extract Plaid sample** (`extract-plaid-sample`) | Inputs `dataset: Plaid dataset`, `infos: PLAID_INFO`; outputs `sample: Plaid sample`, `timesteps: 1D Array` | `split=""`, `sample_number=0` (optional ports) |
| **Extract Plaid time step** (`extract-plaid-time-step`) | Input `sample: PLAID_SAMPLE`; output `mesh: Mesh document` | `time=0.0` (optional port) |
| **Extract Plaid info** (`extract-plaid-info`) | Input `infos: PLAID_INFO`; outputs `owner`, `license`, `data_production`, `data_description`, `num_samples`, `storage_backend` | None |

The loader reads dataset and info metadata from disk. Sample extraction requires
a non-empty split and non-negative sample number. Time-step extraction converts
the selected Plaid tree through Muscat's CGNS bridge. Info outputs may be
optional values depending on the dataset metadata.

The dataset and extracted sample use distinct type IDs (`plaid-dataset` and
`plaid-sample`). The loader's `splits` output lists available dataset keys in
their stored order. Sample extraction returns `get_all_time_values()` as a read-only
NumPy float array in `timesteps`, including shape `(0,)` when no times are available.
Float-list inputs receive explicit array-to-list conversions.