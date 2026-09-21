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
    patterns: object,
) -> tuple[tuple[re.Pattern[str], ...], tuple[re.Pattern[str], ...]]:
    """Parse inclusive and exclusive filename regular expressions from text rules.

    Each non-empty, non-comment line must start with ``+`` or ``include:`` to
    include matching filenames, or ``-`` or ``exclude:`` to exclude them.

    Parameters
    ----------
    patterns : object
        Configured pattern-rule text.

    Returns
    -------
    tuple[tuple[re.Pattern[str], ...], tuple[re.Pattern[str], ...]]
        Compiled inclusive patterns followed by compiled exclusive patterns.

    Raises
    ------
    TypeError
        If the configured rules are not text.
    ValueError
        If a rule lacks a supported prefix, has no regular expression, or
        contains an invalid regular expression.
    """
    if not isinstance(patterns, str):
        raise TypeError("The filename pattern rules must be text")

    inclusive: list[re.Pattern[str]] = []
    exclusive: list[re.Pattern[str]] = []
    for line_number, line in enumerate(patterns.splitlines(), start=1):
        rule = line.strip()
        if not rule or rule.startswith("#"):
            continue

        normalized = rule.casefold()
        if normalized.startswith("include:"):
            target, expression = inclusive, rule[len("include:") :].strip()
        elif normalized.startswith("exclude:"):
            target, expression = exclusive, rule[len("exclude:") :].strip()
        elif rule.startswith("+"):
            target, expression = inclusive, rule[1:].strip()
        elif rule.startswith("-"):
            target, expression = exclusive, rule[1:].strip()
        else:
            raise ValueError(
                f"Filename pattern rule on line {line_number} must start with '+', '-', "
                "'include:', or 'exclude:'"
            )

        if not expression:
            raise ValueError(
                f"Filename pattern rule on line {line_number} has no regular expression"
            )
        try:
            target.append(re.compile(expression))
        except re.error as error:
            raise ValueError(
                f"Invalid filename regular expression on line {line_number}: {error}"
            ) from error

    return tuple(inclusive), tuple(exclusive)


def _read_directory_files(
    inputs: Mapping[str, Any], parameters: Mapping[str, Any]
) -> Mapping[str, Any]:
    """List immediate regular-file names in a directory after regex filtering."""
    directory = Path(inputs["path"]).expanduser()
    if not directory.is_dir():
        raise DirectoryReadError(f"Directory does not exist or is not a directory: {directory}")

    inclusive, exclusive = _compile_filename_patterns(parameters.get("patterns", ""))
    filenames = sorted(path.name for path in directory.iterdir() if path.is_file())
    filtered_filenames = [
        filename
        for filename in filenames
        if (not inclusive or any(pattern.search(filename) for pattern in inclusive))
        and not any(pattern.search(filename) for pattern in exclusive)
    ]
    return {"files": filtered_filenames}


READ_DIRECTORY_FILES = NodeDefinition(
    id="read-directory-files",
    icon="mdi-file-find-outline",
    label="Read Directory Files",
    description="Lists immediate file names in a directory with optional regular-expression filters.",
    ports=(
        PortDefinition("path", PortDirection.INPUT, STRING, "Directory path"),
        PortDefinition("files", PortDirection.OUTPUT, LIST_STR, "File names"),
    ),
    executor=_read_directory_files,
    parameters=(
        ParameterDefinition(
            "patterns",
            ParameterKind.TEXT,
            "Filename patterns",
            "",
            "+\\.csv$\n-exclude-this\\.csv$",
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
