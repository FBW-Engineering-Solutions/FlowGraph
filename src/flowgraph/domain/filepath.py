"""A file path with optional dependent files."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import InitVar, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FilePath:
    """Represent a primary file together with optional dependent files.

    The first path is the primary path used by string and ``os.PathLike``
    operations. Additional paths are retained for integrations that need to
    carry related files alongside the primary file.
    """

    files: list[Path] = field(init=False)
    input_files: InitVar[Path | str | Sequence[Path | str]]

    def __post_init__(self, input_files: Path | str | Sequence[Path | str]) -> None:
        if isinstance(input_files, (str, Path)):
            paths = [input_files]
        else:
            paths = list(input_files)
        if not paths:
            raise ValueError("FilePath requires at least one file")
        self.files = [Path(path) for path in paths]

    @property
    def primary(self) -> Path:
        """Return the primary path represented by this value."""
        return self.files[0]

    def __str__(self) -> str:
        return str(self.primary)

    def __fspath__(self) -> str:
        return self.primary.__fspath__()

    def AddDependentFiles(self, extra_files: Path | str | Sequence[Path | str]) -> None:
        """Append one or more dependent files, preserving their order."""
        if isinstance(extra_files, (str, Path)):
            extra_paths = [extra_files]
        else:
            extra_paths = list(extra_files)
        self.files.extend(Path(path) for path in extra_paths)

    def Compact(self) -> None:
        """Remove duplicate dependent files while retaining first occurrence order."""
        primary = self.primary
        self.files = list(dict.fromkeys([primary, *self.files[1:]]))

    def __getattr__(self, name: str) -> Any:
        """Delegate standard path attributes and methods to the primary path."""
        return getattr(self.primary, name)

    def to_json(self, **kwargs: Any) -> str:
        """Serialize all contained paths to a JSON string."""
        serializable_data = {"files": [str(path) for path in self.files]}
        return json.dumps(serializable_data, **kwargs)

    @classmethod
    def from_json(cls, json_str: str) -> FilePath:
        """Deserialize a :class:`FilePath` from its JSON representation."""
        data = json.loads(json_str)
        files = data.get("files") if isinstance(data, dict) else None
        if (
            not isinstance(files, list)
            or not files
            or not all(isinstance(path, str) for path in files)
        ):
            raise ValueError("FilePath JSON must contain a 'files' array of strings")
        return cls(files)
