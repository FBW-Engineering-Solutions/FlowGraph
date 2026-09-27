---
id: user-guide.importing-data
title: Importing Data
section: User Guide
order: 20
---

# Importing Data

FlowGraph imports external data through reader nodes. Add the reader that matches
your source. Every mesh reader has a required `path` parameter of type **Text**, exported
as an input port. A file can be selected with a **Select file** node and connected
to that port, or the path can be entered directly in a workflow.

Files can also be added to the project from **File → Add files...**. The native
file picker accepts multiple selections. FlowGraph then asks whether to copy the
files into a temporary project folder or link to the original locations. Copies
are removed when the application session ends; linked originals are never deleted
by FlowGraph.

Mesh readers return a `mesh` output containing FlowGraph's canonical **Mesh
document**. The CSV reader returns a `table` output containing a mapping of
column names to NumPy arrays.

## Choosing a reader

| Reader node | Use it for | Input | Output | Dependency |
| --- | --- | --- | --- | --- |
| **Read Mesh (Muscat)** | Mesh formats supported by Muscat's reader factory | `path` parameter/input (`Text`) | `mesh` (`Mesh document`) | Muscat |
| **Read Mesh (MeshIO)** | Mesh formats supported by meshio | `path` parameter/input (`Text`) | `mesh` (`Mesh document`) | meshio and Muscat's meshio bridge |
| **Read Mesh (MeshLane)** | Mesh formats supported by MeshLane | `path` parameter/input (`Text`) | `mesh` (`Mesh document`) | MeshLane and the Muscat MeshLane bridge |
| **Read Table (Pandas)** | Comma-separated tabular data | `path` (`Text`) | `table` (`Table`) | pandas |

Choose **Read Mesh (Muscat)** when the format is supported by Muscat directly
and you want Muscat's extension-aware reader selection. Choose **Read Mesh
(MeshIO)** or **Read Mesh (MeshLane)** when the format is better supported by
one of those libraries. Use **Read Table (Pandas)** for CSV data rather than a
mesh reader.

## Read Mesh (Muscat)

The Muscat reader uses the file extension to select a Muscat reader, then loads
the file into the canonical `MeshDocument` used by FlowGraph. The result is the
editable mesh model; visualization is built later as a derived 3D projection.

```text
Select file.path ──▶ Read Mesh (Muscat).path
                     Read Mesh (Muscat).mesh ──▶ mesh operations
```

Muscat must recognize the file extension and the file contents must be valid for
the selected reader. The path must point to an existing file and must have an
extension.

## Read Mesh (MeshIO)

The MeshIO reader calls `meshio.read(path)` and converts the resulting mesh
through Muscat's MeshIO bridge. The output is still a FlowGraph `MeshDocument`, so
downstream mesh nodes can use it in the same way as output from the Muscat
reader.

Use this reader when meshio provides the format support you need. The `meshio`
package and the corresponding Muscat bridge must be installed in the active
environment.

## Read Mesh (MeshLane)

The MeshLane reader calls MeshLane to read the source and converts the result
through Muscat's MeshLane bridge. It produces the same `mesh` / `Mesh document`
contract as the other mesh readers.

MeshLane is optional. If it is not installed, or if the installed Muscat version
does not provide the MeshLane bridge, execution stops with an actionable error.
Install FlowGraph with the `meshlane` extra when that extra is available in your
environment.

## Read Table (Pandas): CSV

The Pandas reader is intended for `.csv` files containing a header row. It reads
the file with `pandas.read_csv`, then converts each column into a NumPy array.
The node returns a dictionary keyed by the original column names:

```text
table = {
    "x": numpy array,
    "temperature": numpy array,
}
```

The output type is `Table`, not `Mesh document`. Connect it to a node that
expects tabular data; it cannot be connected directly to a mesh operation unless
an explicit conversion or tabular-processing node is provided.

The CSV file must exist and have a filename extension. Ensure pandas is installed
before executing the node. CSV parsing options are currently those provided by
the adapter's default `pandas.read_csv` call.

## File requirements and errors

All four readers validate the path before attempting to parse it:

- The path must identify an existing regular file.
- The path must include a file extension.
- The file must be readable and valid for the selected reader.

If validation, dependency loading, or parsing fails, the node reports a reader-
specific error. Check that the selected node matches the data type and format,
that the file path is correct, and that optional dependencies are installed.

> Keep source data in a location that remains available for the workflow.

See the [interface](interface.md), [workflow node reference](../reference/nodes.md),
or jump to [visualization](visualization.md).