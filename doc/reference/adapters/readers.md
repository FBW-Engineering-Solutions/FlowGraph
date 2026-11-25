---
id: reference.adapters.readers
title: Reader Nodes
section: Reference
order: 13
description: Nodes that load files into FlowGraph data types.
---

# Reader nodes

Mesh readers require a `path: Path` parameter exported as an input port, so it
can be configured directly or connected from a file-path source. The CSV reader
instead requires a `path: Text` input. Readers reject missing or non-file paths;
mesh readers also require a filename extension.

| Node (ID) | Output | Behavior |
| --- | --- | --- |
| **Read Mesh (Muscat)** (`load-muscat`) | `mesh: Mesh document`, `mesh_series: Any`, `available_timesteps: 1D Array` | Lists available times and loads requested snapshots with Muscat's extension-aware reader. |
| **Read Mesh (MeshIO)** (`load-meshio`) | `mesh: Mesh document` | Reads with meshio and converts through Muscat's bridge. |
| **Read Mesh (MeshLane)** (`load-meshlane`) | `mesh: Mesh document` | Reads with the optional MeshLane adapter and bridge. |
| **Read Table (Pandas)** (`load-csv`) | `table: Table` | Reads CSV columns with pandas and returns a mapping of column names to arrays. |
| **Read Table (Pandas)** (`read-table`) | `data: Table document` | Reads an Excel `.xlsx` workbook with pandas and returns a mapping of column names to lists. |

Mesh readers return the canonical editable `MeshDocument`. MeshLane requires
the optional MeshLane dependency and matching Muscat bridge. Reader failures are
reported as actionable `MeshLoadError` messages.

**Read Mesh (Muscat)** exposes a connectable `timestep_to_read` selector:
`first`, `last` (default), or `all`. First and Last use the file's time-step
order and return one mesh. All returns an ordered tuple of `(time, MeshDocument)`
pairs on **Mesh Series** and returns the last snapshot on **Mesh**. The series
output is empty when First or Last is selected. For a static mesh, All returns
one `(None, MeshDocument)` pair; the Mesh output is the same in every mode.

**Available Time Steps** returns a read-only 1D float array in file order,
independent of the selection. If no time steps are reported, it returns `[0.0]`.
An unconnected and unexported time output also defaults to `[0.0]`. A connection
or workflow export counts as a request for an output. Connect only **Available
Time Steps** to inspect metadata without loading geometry or fields. With All
selected, connecting only **Mesh** loads just the last snapshot; connect **Mesh
Series** to load and retain all snapshots.

The Excel reader has `path: Path` (default `input_pandas.xlsx`) and
`sheet_name: Text` (default `Sheet1`) parameter ports. Supply the workbook path
and sheet name directly or connect upstream values. A missing workbook raises
`TableReadError`; pandas uses `openpyxl` to read the selected sheet.