"""Workspace-only file API; this is not a sandbox for workflow Python code."""

from __future__ import annotations

import io
import os
import shutil
import threading
import zipfile
from importlib.resources import files
from pathlib import Path, PurePosixPath

DEMO_FILES = (
    "SpherePoints.csv",
    "FlowGraph.stl",
    "FlowGraph.xdmf",
    "FlowGraph.h5",
    "ColorCardboard.jpg",
)


class Workspace:
    def __init__(self, directory: Path):
        self.root = directory.expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("Workspace must be an existing directory")
        self.lock = threading.RLock()

    def path(self, name: str, *, allow_directory: bool = False) -> Path:
        if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
            raise ValueError("A workspace-relative file path is required")
        relative = PurePosixPath(name)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in name.split("/")):
            raise ValueError("Invalid workspace-relative file path")
        target = self.root
        for part in relative.parts:
            target = target / part
            if target.is_symlink():
                raise ValueError("Symlinks are not allowed in the file API")
        if not target.resolve().is_relative_to(self.root):
            raise ValueError("Path escapes workspace")
        if target.exists() and not target.is_file() and not (allow_directory and target.is_dir()):
            raise ValueError("Only regular files are supported")
        return target

    def listing(self) -> dict:
        with self.lock:
            entries = []
            directories = []
            # Do not follow symlink directories, including on Python 3.11.
            for parent, children, names in os.walk(self.root, followlinks=False):
                children[:] = sorted(
                    name for name in children if not (Path(parent) / name).is_symlink()
                )
                directories.extend(
                    (Path(parent) / name).relative_to(self.root).as_posix() for name in children
                )
                for name in sorted(names):
                    path = Path(parent) / name
                    if path.is_symlink() or not path.is_file():
                        continue
                    entries.append(
                        {
                            "path": path.relative_to(self.root).as_posix(),
                            "name": name,
                            "size": path.stat().st_size,
                            "absolutePath": str(path),
                        }
                    )
            return {
                "files": entries,
                "directories": sorted(directories),
                "directory": str(self.root),
            }

    def write(self, name: str, data: bytes) -> dict:
        with self.lock:
            target = self.path(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            return self.listing()

    def read(self, name: str, limit: int) -> bytes:
        with self.lock:
            target = self.path(name, allow_directory=True)
            if target.is_dir():
                buffer = io.BytesIO()
                total = 0
                with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.write(target, target.name + "/")
                    for parent, children, names in os.walk(target, followlinks=False):
                        children[:] = sorted(
                            child for child in children if not (Path(parent) / child).is_symlink()
                        )
                        for entry in [
                            *(Path(parent) / child for child in children),
                            *(Path(parent) / child for child in sorted(names)),
                        ]:
                            if entry.is_symlink():
                                continue
                            if entry.is_file():
                                total += entry.stat().st_size
                                if total > limit:
                                    raise ValueError("Directory exceeds the download size limit")
                            elif not entry.is_dir():
                                continue
                            archive.write(entry, entry.relative_to(target.parent).as_posix())
                if buffer.tell() > limit:
                    raise ValueError("Archive exceeds the download size limit")
                return buffer.getvalue()
            with target.open("rb") as stream:
                data = stream.read(limit + 1)
            if len(data) > limit:
                raise ValueError("File exceeds the download size limit")
            return data

    def delete(self, name: str) -> dict:
        with self.lock:
            target = self.path(name, allow_directory=True)
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            return self.listing()

    def copy_demos(self) -> dict:
        with self.lock:
            targets = [self.path(name) for name in DEMO_FILES]
            if any(path.exists() for path in targets):
                raise FileExistsError("Demo files already exist; refusing to overwrite")
            contents = [
                files("flowgraph").joinpath("testdata", name).read_bytes() for name in DEMO_FILES
            ]
            for path, data in zip(targets, contents, strict=True):
                path.write_bytes(data)
            return {**self.listing(), "copied": len(targets)}
