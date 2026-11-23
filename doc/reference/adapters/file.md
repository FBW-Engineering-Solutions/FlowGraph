---
id: reference.adapters.file
title: File Nodes
section: Reference
order: 13
description: Nodes that select, download, and enumerate files for workflow inputs.
---

# File nodes

File nodes provide paths for downstream readers and processing nodes. They do not
load file contents themselves, except that **Download URL** retrieves a remote file
and returns the path of the downloaded temporary file.

| Node (ID) | Inputs and outputs | Parameters and behavior |
| --- | --- | --- |
| **Select file** (`select-file`) | Output `path: Text` | `path`: `""`; accepts local file patterns such as `*.*`. The desktop UI opens a local file chooser. |
| **Workspace File** (`workspace-file`) | Optional inputs `workspace: Path` (also Text), `file name: Text`; output `path: Text` | `file name`: `""`. Connected inputs override the runtime workspace and selected relative file without changing the saved selection. |
| **Workspace Folder** (`workspace-folder`) | Optional input `folder: Text` (also Path); output `path: Path` | `folder`: `"."`. Dropdown includes the workspace root and nested subfolders. Connected input overrides only this node without filesystem validation. |
| **Download URL** (`download-url`) | Output `path: Text` | `url`: `""`; accepts only HTTP(S) URLs and downloads the response to a persistent system temporary file. |
| **Read Directory Files** (`read-directory-files`) | Parameter/input `path: Path`; outputs `files: List Text`, `files_full_paths: List Text` | Local `include_pattern` and `exclude_pattern` regular expressions filter immediate regular files by filename. |

## Select file

**Select file** outputs the configured local path without reading it. An empty path
is invalid at execution time. The path can be connected to a reader such as **Read
Mesh (Muscat)** or **Read Image (Pillow)**.

## Workspace File

**Workspace File** (formerly **Select uploaded file**) selects a file within the
active workspace. It stores a relative path such as `my/files/mesh.vtu`, resolves
that path at execution time, and outputs absolute `path` text without reading or
copying file contents. Connect it to the `path` input of **Read Mesh** or another
reader. Moving the workspace does not require editing the saved workflow.

The node ID is `workspace-file` and its parameter is `file name`.
Its optional `workspace` input overrides the configured root for this node only;
connect **Workspace Folder** or supply directory-path text. Its optional `file name` Text input overrides the
selector with a workspace-relative path, for example `meshes/model.vtu`.
Disconnected inputs fall back to the runtime workspace and saved file selection.
Connected values do not replace the saved selection; disconnecting restores it.
When either input is connected, the node only resolves the path: it does not
validate file/directory existence, file kind, or workspace confinement. This allows
new destinations such as `results/output.vtu` to feed writer nodes, even when
the destination directory does not exist yet. It does not create files or folders;
the downstream writer is responsible for them. Input types and nonempty values
are still required, and relative file paths still need a workspace root.
Existing absolute paths remain external references. In the web
editor, exact matches to current workspace files are normalized to relative paths;
ambiguous basenames and unmatched external paths are not rewritten.

Configure the root with `flowgraph run workflow.json --workspace ./project`,
`flowgraph serve --workspace ./project`, or the Python execution APIs' `workspace`
keyword. Browser execution uses its uploaded/mounted files directory. Desktop
launchers accept `--workspace ./project`; without it, Desktop uses its temporary
session upload folder. Persistent workspace files are not removed on exit.

Without connected inputs, relative selections require an explicit workspace and
an existing regular file. Traversal or symlinks escaping that workspace are
rejected for these selector values. Legacy absolute paths
are intentionally not confined to it. No `{workspace}` substitution is performed
in arbitrary text parameters; use the node's output instead.

## Workspace Folder

Use **Workspace Folder** when you need a directory rather than a selected file.
Choose **Workspace root** (`.`) or any nested subdirectory in its dropdown,
including empty directories. The saved `folder` value is an ordinary
workspace-relative Text parameter, not a separate data type;
the node outputs its absolute runtime directory as `path: Path` (`pathlib.Path`), without reading
files or creating directories. For example, connect
`Workspace Folder.path → Read Directory Files.path` to enumerate selected files.
The root comes from the same runtime configuration as **Workspace File** and is
inherited by nested workflows. An unconfigured workspace produces a clear error;
there is no implicit fallback to the process working directory. Moving the
workspace updates the output on the next run, including incremental execution.
The optional `folder` input accepts Text or Path and overrides only this node,
not the runtime workspace or other graph branches. Relative inputs resolve against
the runtime workspace; absolute inputs work without a configured workspace.
Connected paths skip existence, directory-kind and workspace-confinement checks,
allowing new output directories. No directories are created. Empty text and invalid
input types are rejected. The saved dropdown selection is preserved and restored
when the input is disconnected.

Without a connected input, missing folders, file selections, absolute paths and
paths escaping the workspace are rejected. The node ID is `workspace-folder`; nodes without a
`folder` parameter continue to select the workspace root.

## Download URL

**Download URL** accepts an HTTP or HTTPS URL. It stores the response in a persistent
system temporary file, preserves a suffix from the URL when possible, and outputs the
local path. Invalid URL schemes, empty URLs, failed requests, and unsuccessful HTTP
responses are reported as execution errors.

In the browser runtime, URL downloads require JavaScript Promise Integration (JSPI)
and the target server must allow the request through its CORS policy.

## Read Directory Files

**Read Directory Files** returns sorted basenames in `files` and their resolved
full paths in `files_full_paths` for immediate regular files in the configured
directory. It does not include nested files or directory names. The optional
`path` parameter/input has type **Path** (`pathlib.Path`), not **FilePath**, and
must identify an existing directory. **Workspace Folder** connects directly without
conversion. Saved directory parameters remain JSON strings and are converted to
paths for execution.

The local `include_pattern` and `exclude_pattern` parameters each accept a
regular expression. For example, to include CSV and text files except generated
CSVs, configure:

```text
include_pattern = \.(csv|txt)$
exclude_pattern = \.generated\.csv$
```

An empty include pattern admits all immediate files. The exclude pattern takes
precedence over the include pattern. Both filters match against filenames, not
their full paths.