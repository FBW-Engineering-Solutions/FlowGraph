"""Dependency tokens for declared files and bounded recursive directories."""

from collections.abc import Mapping
from functools import partial
from hashlib import sha256
from os import scandir
from pathlib import Path
from stat import S_ISDIR, S_ISREG
from typing import Any

from flowgraph.domain.filepath import FilePath

MAX_DIRECTORY_FILES = 1000


def single_file_dependency(inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> tuple:
    """Hash file content or snapshot recursive directory metadata.

    Explicit FilePath companions are included; hidden format dependencies are
    not discovered. Metadata is checked around streaming to reject unstable files.
    """
    value = inputs.get("path", parameters.get("path", ""))
    if isinstance(value, FilePath) and len(value.files) != 1:
        return tuple(_file_fingerprint(path) for path in value.files)
    return _file_fingerprint(value)


def _file_fingerprint(value: Any) -> tuple:
    """Fingerprint a file or directory without guessing format dependencies."""
    if isinstance(value, FilePath) and len(value.files) != 1:
        raise ValueError("Single-file dependency cannot fingerprint companion files")
    path = Path(value).expanduser().resolve(strict=True)
    before = path.stat()
    if S_ISDIR(before.st_mode):
        return _directory_metadata(path)
    if not S_ISREG(before.st_mode):
        raise ValueError(f"File dependency is not a regular file: {path}")
    digest = sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise ValueError("File changed while fingerprinting")
    return (_file_metadata(path), digest.hexdigest())


def _declared_file_dependencies(
    inputs: Mapping[str, Any], parameters: Mapping[str, Any], *, names: tuple[str, ...]
) -> tuple:
    """Fingerprint declared file fields, including explicitly carried companions."""
    tokens = []
    for name in names:
        value = inputs.get(name, parameters.get(name, ""))
        paths = value.files if isinstance(value, FilePath) else (value,)
        tokens.append((name, tuple(_file_fingerprint(path) for path in paths)))
    return tuple(tokens)


def declared_file_dependencies(names: tuple[str, ...]):
    """Build a resolver for typed file inputs/parameters, never arbitrary strings.

    Unlisted companions must update the principal file timestamp when changed.
    """
    if names == ("path",):
        return single_file_dependency
    return partial(_declared_file_dependencies, names=names)


def _file_metadata(value: Any) -> tuple:
    """Cheap identity/timestamp token; deliberately exclude access time."""
    path = Path(value).expanduser().resolve(strict=True)
    info = path.stat()
    if S_ISDIR(info.st_mode):
        return _directory_metadata(path)
    if not S_ISREG(info.st_mode):
        raise ValueError(f"File dependency is not a regular file: {path}")
    return (str(path), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _directory_metadata(path: Path) -> tuple:
    """Snapshot at most 1,000 files; incomplete/unsafe trees cannot be cached.

    Sort only the bounded final file list, not the potentially unbounded directory
    listing. Reject nested symlinks rather than omit dependencies or follow cycles.
    Errors propagate to the session's existing uncacheable-dependency handling.
    """
    root = path.stat()
    files = []
    pending = [path]
    while pending:
        with scandir(pending.pop()) as entries:
            for entry in entries:
                if entry.is_symlink():
                    raise ValueError(f"Directory dependency contains a symlink: {entry.path}")
                info = entry.stat(follow_symlinks=False)
                if S_ISDIR(info.st_mode):
                    pending.append(Path(entry.path))
                elif S_ISREG(info.st_mode):
                    if len(files) == MAX_DIRECTORY_FILES:
                        raise ValueError(
                            f"Directory dependency exceeds {MAX_DIRECTORY_FILES} files: {path}"
                        )
                    files.append(
                        (
                            Path(entry.path).relative_to(path).as_posix(),
                            info.st_mtime_ns,
                            info.st_size,
                        )
                    )
                else:
                    raise ValueError(f"Directory dependency contains a non-file: {entry.path}")
    return ("directory", str(path), root.st_dev, root.st_ino, tuple(sorted(files)))


def declared_dependency_metadata(
    resolver, inputs: Mapping[str, Any], parameters: Mapping[str, Any]
):
    """Return a cheap precheck for built-in resolvers; custom resolvers stay opaque."""
    if resolver is single_file_dependency:
        names = ("path",)
    elif isinstance(resolver, partial) and resolver.func is _declared_file_dependencies:
        names = resolver.keywords["names"]
    else:
        return None
    tokens = []
    for name in names:
        value = inputs.get(name, parameters.get(name, ""))
        paths = value.files if isinstance(value, FilePath) else (value,)
        tokens.append((name, tuple(_file_metadata(path) for path in paths)))
    return tuple(tokens)
