"""Workflow nodes for selecting files and listing directory contents."""

import re
from collections.abc import Mapping
from pathlib import Path, PureWindowsPath
from typing import Any

from flowgraph.application.workflow_core import (
    ExecContext,
    NodeDefinition,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
)

from .data_types import DIRECTORY, LIST_STR, STRING, ParameterKind


def _select_file(
    _inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Output the configured local file path."""
    path = parameters.get("path", "")
    if not isinstance(path, str):
        raise TypeError("The selected file path parameter must be text")
    if len(path) == 0:
        raise ValueError("Path can't be empty")
    return {"path": path}


SELECT_FILE = NodeDefinition(
    cache_policy="pure",
    id="select-file",
    requirements=(),
    icon="mdi-file-find-outline",
    label="Select file",
    description="Outputs a selected local file path as text without reading the file.",
    ports=(PortDefinition("path", PortDirection.OUTPUT, STRING, "File path"),),
    executor=_select_file,
    parameters=(
        ParameterDefinition(
            "path",
            ParameterKind.FILE,
            "File path",
            "",
            "/path/to/file",
            file_patterns=("*.*",),
        ),
    ),
)


def _select_server_file(
    _inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Resolve a portable workspace file, preserving legacy absolute paths."""
    path = parameters.get("file name", "")
    if not isinstance(path, str):
        raise TypeError("The selected file path parameter must be text")
    if len(path) == 0:
        raise ValueError("Path can't be empty")
    source = Path(path).expanduser()
    # Absolute paths from existing workflows remain external references.
    if source.is_absolute():
        return {"path": str(source)}
    root = _exec_context.workspace if _exec_context is not None else None
    if root is None:
        raise ValueError("Workspace File requires a configured workspace directory")
    source = (root / source).resolve()
    if not source.is_relative_to(root):
        raise ValueError("Workspace File path escapes the workspace directory")
    if not source.is_file():
        raise ValueError(f"Workspace file does not exist or is not a file: {path}")
    return {"path": str(source)}


SELECT_SERVER_FILE = NodeDefinition(
    cache_policy="pure",
    id="workspace-file",
    requirements=(),
    icon="mdi-cloud-upload-outline",
    label="Workspace File",
    description="Resolves a workspace-relative file path at runtime without reading the file. Legacy absolute paths remain external references.",
    ports=(PortDefinition("path", PortDirection.OUTPUT, STRING, "File path"),),
    executor=_select_server_file,
    parameters=(
        ParameterDefinition(
            "file name", ParameterKind.SELECT_SERVER_FILENAME, "Workspace file", "", port=False
        ),
    ),
)


class DirectoryReadError(ValueError):
    """Raised when a directory-file listing node receives an invalid directory path."""


def _workspace_directory(
    _inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Resolve the selected relative folder within the host-configured workspace."""
    root = _exec_context.workspace if _exec_context is not None else None
    if root is None:
        raise ValueError("Workspace Folder requires a configured workspace directory")
    selected = parameters.get("folder", ".")
    if not isinstance(selected, str):
        raise TypeError("Workspace Folder selection must be text")
    relative = Path(selected)
    if relative.is_absolute() or PureWindowsPath(selected).anchor:
        raise ValueError("Workspace Folder requires a workspace-relative folder path")
    folder = (root / relative).resolve()
    if not folder.is_relative_to(root):
        raise ValueError("Workspace Folder path escapes the workspace directory")
    if not folder.is_dir():
        raise ValueError(f"Workspace folder does not exist or is not a directory: {selected}")
    return {"path": folder}


WORKSPACE = NodeDefinition(
    cache_policy="pure",
    id="workspace-folder",
    requirements=(),
    icon="mdi-folder-outline",
    label="Workspace Folder",
    description="Resolves a selected workspace-relative folder as an absolute directory path. Defaults to the workspace root.",
    ports=(PortDefinition("path", PortDirection.OUTPUT, DIRECTORY, "Directory path"),),
    executor=_workspace_directory,
    parameters=(
        ParameterDefinition("folder", ParameterKind.TEXT, "Workspace folder", ".", port=False),
    ),
)


def _compile_filename_patterns(
    pattern: object,
) -> re.Pattern[str] | None:
    """Compile independent inclusive and exclusive filename regular expressions.

    Empty text disables the corresponding filter.

    Parameters
    ----------
    pattern : object
        One configured regular-expression text value. Empty text disables that
        filter.

    Returns
    -------
    re.Pattern[str] | None
        The compiled regular expression, or ``None`` for empty text.

    Raises
    ------
    TypeError
        If the configured rules are not text.
    ValueError
        If the configured value is not text or contains an invalid regular
        expression.
    """
    if not isinstance(pattern, str):
        raise TypeError("The filename pattern must be text")
    expression = pattern.strip()
    if not expression:
        return None
    try:
        return re.compile(expression)
    except re.error as error:
        raise ValueError(f"Invalid filename regular expression: {error}") from error


def _read_directory_files(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """List immediate regular-file names in a directory after regex filtering."""
    directory = Path(inputs.get("path", parameters.get("path", ""))).expanduser()
    if not directory.is_dir():
        raise DirectoryReadError(f"Directory does not exist or is not a directory: {directory}")

    include_pattern = _compile_filename_patterns(parameters.get("include_pattern", ""))
    exclude_pattern = _compile_filename_patterns(parameters.get("exclude_pattern", ""))
    filenames = sorted(path.name for path in directory.iterdir() if path.is_file())
    filtered_filenames = [
        filename
        for filename in filenames
        if (include_pattern is None or include_pattern.search(filename))
        and (exclude_pattern is None or not exclude_pattern.search(filename))
    ]
    return {
        "files": filtered_filenames,
        "files_full_paths": [
            str((directory / filename).resolve()) for filename in filtered_filenames
        ],
    }


READ_DIRECTORY_FILES = NodeDefinition(
    cache_policy="always",
    id="read-directory-files",
    requirements=(),
    icon="mdi-file-find-outline",
    label="Read Directory Files",
    description="Lists immediate file names in a directory with optional regular-expression filters.",
    ports=(
        PortDefinition("files", PortDirection.OUTPUT, LIST_STR, "File names"),
        PortDefinition(
            "files_full_paths",
            PortDirection.OUTPUT,
            LIST_STR,
            "Filtered file full paths",
        ),
    ),
    executor=_read_directory_files,
    parameters=(
        ParameterDefinition(
            "path",
            ParameterKind.DIRECTORY,
            "Directory path",
            "",
            "/path/to/directory",
            port=True,
        ),
        ParameterDefinition(
            "include_pattern",
            ParameterKind.TEXT,
            "Include pattern",
            "",
            r"\\.csv$",
            port=False,
        ),
        ParameterDefinition(
            "exclude_pattern",
            ParameterKind.TEXT,
            "Exclude pattern",
            "",
            "exclude-this",
            port=False,
        ),
    ),
)


__all__ = [
    "READ_DIRECTORY_FILES",
    "SELECT_FILE",
    "SELECT_SERVER_FILE",
    "WORKSPACE",
    "DirectoryReadError",
]
