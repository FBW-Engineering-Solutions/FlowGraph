---
id: reference.adapters.file-conversion
title: File Conversion Nodes
section: Reference
order: 17
description: Convert mesh files between formats supported by the configured readers and writers.
---

# File-conversion nodes

## Convert Mesh File Format (`convert-mesh-file-format`)

The **Convert Mesh File Format** node reads a mesh with the selected reader,
writes it with the selected writer, and preserves supported point and element
fields during the conversion.

| Direction | Port or parameter | Type | Default | Description |
| --- | --- | --- | --- | --- |
| Input port | `input_filename` | `Path` | — | Existing source mesh file. |
| Input port | `output_filename` | `Path` | — | Destination mesh filename. Its parent directory must already exist. |
| Output port | `converted_filename` | `Path` | — | Destination filename returned after conversion. |
| Parameter | `reader` | `select str` | `auto` | Reader selection. `auto` chooses a reader from the input extension and prefers a Muscat reader when both Muscat and MeshIO entries are available. |
| Parameter | `writer` | `select str` | `auto` | Writer selection. `auto` chooses a writer from the output extension and prefers a Muscat writer when both choices are available. |
| Parameter | `timestep_to_read` | `select str` | `last` | Selects `first`, `last`, or `all` for temporal readers. |
| Parameter | `binary` | `Boolean` | `True` | Requests binary output when the selected writer supports it. |

The source path must identify an existing file and both filenames must have an
extension. The destination directory is not created automatically. Reader and
writer implementations are loaded lazily, so formats whose optional backend is
not installed fail only when that format is selected or resolved automatically.

## Format selection

With `reader=auto` or `writer=auto`, the node uses the filename extension to
select a registered implementation. When an extension has both Muscat and
MeshIO registrations, the Muscat implementation is preferred. Explicit
selection can be used with the complete catalog key shown in the node parameter
options, for example a key beginning with `.mesh Muscat` or `.vtk MeshIO`.

The available formats depend on the installed Muscat and MeshIO integrations.
The node does not convert through a separate intermediate file; it reads with
the selected reader and writes directly with the selected writer.

For example, an STL file can be converted directly to MEDIT binary `.meshb`
using either of these explicit reader/writer pairs when both integrations are
installed:

| Reader | Writer |
| --- | --- |
| `.stl Muscat StlReader` | `.meshb Muscat MeshWriter` |
| `.stl MeshIO stl_stl_Reader` | `.meshb MeshIO meshb_medit_Writer` |

The MeshIO reader and writer entries are initialized when they are first used.
MeshIO writers use the format's MeshIO defaults when they do not expose a
`SetBinary` operation; the `binary` parameter still applies to writers that
support that operation.

## Temporal data

For readers that support temporal data:

- `first` writes the first available time step.
- `last` writes the last available time step.
- `all` writes every available time step when the writer supports temporal data.

If the selected writer does not support temporal output, the conversion writes a
single mesh using the reader's current read state. Writer resources are closed
when the conversion finishes, including when writing raises an error.

## Example

```text
Select file.path ──▶ Convert Mesh File Format.input_filename
Set output path ────▶ Convert Mesh File Format.output_filename
                                       converted_filename ──▶ downstream file node
```

Use a destination filename with the desired output extension, for example
`converted.vtk`, `converted.mesh`, or `converted.meshb`. The destination path is
returned as `converted_filename` after a successful conversion.

The integration test suite verifies both explicit STL-to-`.meshb` pairs with
Muscat's `stlsphere.stl` fixture obtained through
`Muscat.TestData.GetTestDataPath()`.