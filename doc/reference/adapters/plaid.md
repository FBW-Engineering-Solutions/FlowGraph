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
| **Load Plaid Dataset** (`load-plaid-dataset`) | Outputs `dataset: Plaid sample`, `infos: Plaid info` | `path=""` (optional input port) |
| **Extract Plaid sample** (`extract-plaid-sample`) | Inputs `dataset: PLAID_SAMPLE`, `infos: PLAID_INFO`; output `sample: Plaid sample` | `split=""`, `sample_number=0` (optional ports) |
| **Extract Plaid time step** (`extract-plaid-time-step`) | Input `sample: PLAID_SAMPLE`; output `mesh: Mesh document` | `time=0.0` (optional port) |
| **Extract Plaid info** (`extract-plaid-info`) | Input `infos: PLAID_INFO`; outputs `owner`, `license`, `data_production`, `data_description`, `num_samples`, `storage_backend` | None |

The loader reads dataset and info metadata from disk. Sample extraction requires
a non-empty split and non-negative sample number. Time-step extraction converts
the selected Plaid tree through Muscat's CGNS bridge. Info outputs may be
optional values depending on the dataset metadata.