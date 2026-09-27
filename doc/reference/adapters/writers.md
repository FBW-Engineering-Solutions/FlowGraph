---
id: reference.adapters.writers
title: Writer Nodes
section: Reference
order: 18
description: Nodes that export canonical mesh documents.
---

# Writer nodes

Mesh writers require a `path: Path` parameter exported as an input port and a
`mesh: Mesh document` input. Writers have no outputs.

| Node (ID) | Writer |
| --- | --- |
| **Write Mesh (Muscat)** (`write-muscat`) | Muscat universal writer selected by extension |
| **Write Mesh (MeshIO)** (`write-meshio`) | meshio through Muscat's meshio bridge |
| **Write Mesh (MeshLane)** (`write-meshlane`) | Optional MeshLane adapter |

Destinations must have a filename extension and an existing parent directory.
MeshLane requires the optional dependency and Muscat bridge. Failures are
reported as actionable `MeshWriteError` messages.

## Write Table (Pandas) (`write-table`)

Accepts `data: Table document` as a required input and writes an Excel `.xlsx`
workbook without a row index. The `path: Path` parameter (default
`output_pandas.xlsx`) and `sheet_name: Text` parameter (default `Sheet1`) are
input ports; `header: Boolean` defaults to `True` and is local to the node.
The node has no outputs. The destination directory must already exist. pandas
uses `openpyxl` to write the workbook; invalid table data or write errors raise
`TableWriteError`.