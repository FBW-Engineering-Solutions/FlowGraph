"""Workflow nodes for selecting files and listing directory contents."""

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from flowgraph.application.workflow_core import (
    NodeDefinition,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
)

from .data_types import LIST_STR, STRING, ParameterKind


def _select_file(_inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Output the configured local file path."""
    path = parameters.get("path", "")
    if not isinstance(path, str):
        raise TypeError("The selected file path parameter must be text")
    if len(path) == 0:
        raise ValueError("Path can't be empty")
    return {"path": path}


SELECT_FILE = NodeDefinition(
    id="select-file",
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
    _inputs: Mapping[str, Any], parameters: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Output the configured uploaded-file path."""
    path = parameters.get("file name", "")
    if not isinstance(path, str):
        raise TypeError("The selected file path parameter must be text")
    if len(path) == 0:
        raise ValueError("Path can't be empty")
    return {"path": path}


SELECT_SERVER_FILE = NodeDefinition(
    id="select-server-file",
    icon="mdi-cloud-upload-outline",
    label="Select uploaded file",
    description="Outputs a selected server file path as text without reading the file.",
    ports=(PortDefinition("path", PortDirection.OUTPUT, STRING, "File path"),),
    executor=_select_server_file,
    parameters=(
        ParameterDefinition(
            "file name", ParameterKind.SELECT_SERVER_FILENAME, "File Name", "", port=False
        ),
    ),
)


class DirectoryReadError(ValueError):
    """Raised when a directory-file listing node receives an invalid directory path."""


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
    inputs: Mapping[str, Any], parameters: Mapping[str, Any]
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
    id="read-directory-files",
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
            ParameterKind.FILE,
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
    "DirectoryReadError",
]
