"""Opt-in workspace-local wheel installation; never mutate the server environment."""

from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import zipfile
from importlib import metadata
from pathlib import Path
from urllib.request import Request, urlopen

from packaging.utils import canonicalize_name

from flowgraph.application import wasm_packages


def package_directory(workspace: Path) -> Path:
    """Different interpreters/ABIs/platforms never share installed binaries."""
    identity = f"{sys.implementation.cache_tag}-{sysconfig.get_platform()}"
    return workspace / ".flowgraph-packages" / identity / "site-packages"


def checked_directory(workspace: Path) -> Path:
    target = package_directory(workspace)
    for path in [target, *target.parents]:
        if path == workspace:
            break
        if path.is_symlink():
            raise PermissionError("Extra-package directory must not be a symbolic link")
    return target


class PackageManager:
    def __init__(self, workspace: Path, *, enabled=False):
        self.workspace = workspace
        self.enabled = enabled
        self.pending = None

    def info(self):
        target = checked_directory(self.workspace)
        parent = target
        while not parent.exists():
            parent = parent.parent
        writable = bool(parent.stat().st_mode & 0o222) and os.access(parent, os.W_OK)
        if target.parent.exists():
            writable = (
                writable
                and bool(target.parent.stat().st_mode & 0o222)
                and os.access(target.parent, os.W_OK)
            )
        return {
            "enabled": self.enabled and writable,
            "reason": ""
            if self.enabled and writable
            else (
                "Workspace package directory is read-only."
                if self.enabled
                else "Restart the server with --allow-package-install to enable installation."
            ),
            "destination": str(target),
            "persistent": True,
        }

    def distributions(self):
        target = checked_directory(self.workspace)
        return list(metadata.distributions(path=[str(target)])) if target.is_dir() else []

    def installed(self, name):
        # Base environment always wins; never shadow its distributions.
        try:
            return metadata.version(name)
        except metadata.PackageNotFoundError:
            return next(
                (
                    item.version
                    for item in self.distributions()
                    if canonicalize_name(item.metadata["Name"]) == canonicalize_name(name)
                ),
                None,
            )

    async def fetch(self, url, *, binary=False):
        def download():
            try:
                with urlopen(
                    Request(url, headers={"User-Agent": "FlowGraph-package-installer"}), timeout=30
                ) as response:
                    if not response.url.startswith(
                        ("https://pypi.org/", "https://files.pythonhosted.org/")
                    ):
                        raise ValueError("Unexpected package download redirect")
                    data = response.read((200 << 20) + 1)
                    if len(data) > 200 << 20:
                        raise ValueError("Package download limit exceeded (200 MiB)")
                    return data if binary else json.loads(data)
            except OSError as error:
                raise ValueError(f"Package download failed: {error}") from error

        return await asyncio.to_thread(download)

    def require_enabled(self):
        info = self.info()
        if not info["enabled"]:
            raise PermissionError(info["reason"])

    def check(self, name):
        self.require_enabled()
        self.pending = None
        pending = {}
        result = asyncio.run(
            asyncio.wait_for(
                wasm_packages.check_package(
                    name,
                    native=True,
                    installed_lookup=self.installed,
                    fetcher=self.fetch,
                    pending_store=pending,
                ),
                100,
            )
        )
        self.pending = pending
        result.update(destination=str(checked_directory(self.workspace)), persistent=True)
        return result

    def install(self, token):
        self.require_enabled()
        if (
            not isinstance(token, str)
            or self.pending is None
            or token != self.pending["result"]["token"]
        ):
            raise ValueError("Package check expired. Check availability again.")
        plan, self.pending = self.pending, None
        for item in plan["result"]["packages"]:
            if self.installed(item["name"]) != (item["version"] if item["installed"] else None):
                raise ValueError("Installed packages changed. Check availability again.")
        target = checked_directory(self.workspace)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=target.parent, prefix="install-") as temporary:
            root = Path(temporary)
            staged = root / "site-packages"
            if target.exists():
                if any(path.is_symlink() for path in target.rglob("*")):
                    raise PermissionError("Extra-package directory contains symbolic links")
                shutil.copytree(target, staged)
            else:
                staged.mkdir()
            wheels = []
            occupied = {path.name for path in staged.iterdir()}
            for filename, data in plan["wheels"].values():
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    roots = {path.split("/")[0] for path in archive.namelist()}
                    for path in archive.namelist():
                        parts = path.split("/")
                        if (
                            len(parts) >= 3
                            and parts[0].endswith(".data")
                            and parts[1] in {"purelib", "platlib"}
                        ):
                            roots.add(parts[2])
                    if roots & occupied:
                        raise ValueError(
                            "Wheel contents conflict with existing workspace packages."
                        )
                    occupied.update(roots)
                wheel = root / filename
                wheel.write_bytes(data)
                wheels.append(str(wheel))
            if wheels:
                # uv is a deliberate server optional dependency, not a shell command.
                import uv

                process = subprocess.run(
                    [
                        uv.find_uv_bin(),
                        "--no-config",
                        "--no-cache",
                        "pip",
                        "install",
                        "--python",
                        sys.executable,
                        "--target",
                        str(staged),
                        "--no-deps",
                        "--no-index",
                        "--only-binary",
                        ":all:",
                        *wheels,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=100,
                    check=False,
                    env={
                        key: value
                        for key, value in os.environ.items()
                        if not key.startswith(("UV_", "PIP_"))
                    },
                )
                if process.returncode:
                    raise ValueError(f"Wheel installation failed: {process.stderr[-4000:]}")
            # Prevent package contents from shadowing already installed base modules.
            import importlib.util

            for item in staged.iterdir():
                module = item.name.split(".")[0]
                if (
                    (item.is_dir() or item.suffix in {".py", ".so", ".pyd"})
                    and module.isidentifier()
                    and item.name != "__pycache__"
                    and not item.name.endswith((".dist-info", ".data", ".libs"))
                ):
                    spec = importlib.util.find_spec(module)
                    if spec is not None:
                        raise ValueError(f"Package would shadow existing Python module: {module}")
            backup = root / "previous"
            if target.exists():
                target.rename(backup)
            try:
                staged.rename(target)
            except BaseException:
                if backup.exists():
                    backup.rename(target)
                raise
        return plan["result"]
