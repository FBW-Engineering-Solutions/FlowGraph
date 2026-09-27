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
| **Read Mesh (Muscat)** (`load-muscat`) | `mesh: Mesh document` | Uses Muscat's extension-aware universal reader. |
| **Read Mesh (MeshIO)** (`load-meshio`) | `mesh: Mesh document` | Reads with meshio and converts through Muscat's bridge. |
| **Read Mesh (MeshLane)** (`load-meshlane`) | `mesh: Mesh document` | Reads with the optional MeshLane adapter and bridge. |
| **Read Table (Pandas)** (`load-csv`) | `table: Table` | Reads CSV columns with pandas and returns a mapping of column names to arrays. |
| **Read Table (Pandas)** (`read-table`) | `data: Table document` | Reads an Excel `.xlsx` workbook with pandas and returns a mapping of column names to lists. |

Mesh readers return the canonical editable `MeshDocument`. MeshLane requires
the optional MeshLane dependency and matching Muscat bridge. Reader failures are
reported as actionable `MeshLoadError` messages.

The Excel reader has `path: Path` (default `input_pandas.xlsx`) and
`sheet_name: Text` (default `Sheet1`) parameter ports. Supply the workbook path
and sheet name directly or connect upstream values. A missing workbook raises
`TableReadError`; pandas uses `openpyxl` to read the selected sheet.