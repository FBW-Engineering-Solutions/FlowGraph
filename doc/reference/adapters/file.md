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
| **Select uploaded file** (`select-server-file`) | Output `path: Text` | `file name`: `""` (UI-only, not a port). The server-side upload selector displays uploaded files and returns the selected server path. |
| **Download URL** (`download-url`) | Output `path: Text` | `url`: `""`; accepts only HTTP(S) URLs and downloads the response to a persistent system temporary file. |
| **Read Directory Files** (`read-directory-files`) | Parameter/input `path: Path`; outputs `files: List Text`, `files_full_paths: List Text` | Local `include_pattern` and `exclude_pattern` regular expressions filter immediate regular files by filename. |

## Select file

**Select file** outputs the configured local path without reading it. An empty path
is invalid at execution time. The path can be connected to a reader such as **Read
Mesh (Muscat)** or **Read Image (Pillow)**.

## Select uploaded file

**Select uploaded file** is intended for files uploaded to the FlowGraph server. The
`file name` parameter is a UI-only selector and is not exported as a workflow input
port. The node outputs the selected server-side path as text and does not read the
file.

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
`path` parameter port must identify an existing directory.

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