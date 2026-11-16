"""Wheel-only package resolution and confirmed Pyodide installation.

Checking downloads and inspects wheels, but never imports or installs them.
Only the checked bytes are installed after explicit confirmation.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import io
import platform
import re
import tempfile
import zipfile
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import urlsplit

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

_pending: dict | None = None
_MAX_BYTES = 200 * 1024 * 1024
_catalog_versions: dict[str, str] = {}


async def _fetch(url: str, *, binary: bool = False):
    from pyodide.http import pyfetch

    response = await pyfetch(url, credentials="omit")
    if not response.ok:
        raise ValueError(f"Package download failed (HTTP {response.status}).")
    return await response.bytes() if binary else await response.json()


def _installed(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return _catalog_versions.get(name)


async def check_package(
    name: str,
    *,
    native=False,
    catalog=None,
    installed_lookup=None,
    fetcher=None,
    pending_store=None,
) -> dict:
    """Resolve conservatively; never replace installed packages or build sources.

    This deliberately has no backtracking or extras support. A conflicting graph
    is rejected rather than silently changing the selected versions.
    """
    global _pending
    catalog = catalog or {}
    installed_lookup = installed_lookup or _installed
    fetcher = fetcher or _fetch
    if pending_store is None:
        _pending = None
    else:
        pending_store.clear()
    if not isinstance(name, str) or not re.fullmatch(
        r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,198}[A-Za-z0-9])?", name
    ):
        raise ValueError("Enter a PyPI package name only (no URLs, extras, or version specifiers).")
    name = canonicalize_name(name)
    selected: dict[str, dict] = {}
    wheels: dict[str, tuple[str, bytes]] = {}
    environment = default_environment()
    environment["extra"] = ""
    supported = set(sys_tags())
    total_bytes = 0
    catalog_names = []

    async def visit(requirement: Requirement):
        nonlocal total_bytes
        if requirement.marker and not requirement.marker.evaluate(environment):
            return
        if requirement.url or requirement.extras:
            raise ValueError(f"Dependency URLs and extras are not supported: {requirement}")
        key = canonicalize_name(requirement.name)
        if key in selected:
            if Version(selected[key]["version"]) not in requirement.specifier:
                raise ValueError(f"Conflicting dependency: {requirement}. No packages installed.")
            return
        if len(selected) >= 50:
            raise ValueError("Package dependency limit exceeded (50).")
        installed = installed_lookup(key)
        if installed is not None:
            if Version(installed) not in requirement.specifier:
                raise ValueError(f"{requirement} conflicts with installed {key} {installed}.")
            selected[key] = {
                "name": key,
                "version": installed,
                "installed": True,
                "kind": "installed",
            }
            return
        if key in catalog:
            entry = catalog[key]
            if Version(entry["version"]) not in requirement.specifier:
                raise ValueError(f"{requirement} conflicts with the pinned Pyodide catalog.")
            url = entry["file_name"]
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or parsed.netloc != "cdn.jsdelivr.net"
                or not parsed.path.startswith("/pyodide/v0.29.4/full/")
            ):
                raise ValueError("Unexpected Pyodide catalog artifact source.")
            data = await fetcher(url, binary=True)
            total_bytes += len(data)
            if total_bytes > _MAX_BYTES or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise ValueError("Catalog artifact size or SHA-256 integrity check failed.")
            selected[key] = {
                "name": key,
                "version": entry["version"],
                "installed": False,
                "kind": "python" if entry["file_name"].endswith("none-any.whl") else "wasm",
            }
            for dependency in entry.get("depends", []):
                await visit(Requirement(dependency))
            catalog_names.append(key)
            return
        project = await fetcher(f"https://pypi.org/pypi/{key}/json")
        candidates = []
        for version_text, files in project["releases"].items():
            version = Version(version_text)
            if (
                version.is_prerelease
                or version.is_devrelease
                or version not in requirement.specifier
            ):
                continue
            for file in files:
                if file.get("yanked") or file.get("packagetype") != "bdist_wheel":
                    continue
                if platform.python_version() not in SpecifierSet(file.get("requires_python") or ""):
                    continue
                wheel_name, wheel_version, _, tags = parse_wheel_filename(file["filename"])
                if canonicalize_name(wheel_name) != key or wheel_version != version:
                    continue
                if not tags.intersection(supported) or (
                    not native and any(tag.abi != "none" or tag.platform != "any" for tag in tags)
                ):
                    continue
                candidates.append((version, file))
        if not candidates:
            raise ValueError(
                f"No compatible {'native' if native else 'pure-Python or WebAssembly'} wheel available for {requirement}."
            )
        version, file = max(candidates, key=lambda item: item[0])
        url = file["url"]
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "files.pythonhosted.org":
            raise ValueError("Unexpected PyPI download host.")
        if total_bytes + file.get("size", _MAX_BYTES + 1) > _MAX_BYTES:
            raise ValueError("Package download limit exceeded (200 MiB).")
        data = await fetcher(url, binary=True)
        total_bytes += len(data)
        if (
            total_bytes > _MAX_BYTES
            or hashlib.sha256(data).hexdigest() != file["digests"]["sha256"]
        ):
            raise ValueError("Wheel size or SHA-256 integrity check failed.")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            metadata_files = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
            if len(metadata_files) != 1:
                raise ValueError("Wheel must contain exactly one METADATA file.")
            if archive.getinfo(metadata_files[0]).file_size > 1024 * 1024:
                raise ValueError("Wheel metadata exceeds the 1 MiB limit.")
            metadata = BytesParser().parsebytes(archive.read(metadata_files[0]))
        if canonicalize_name(metadata["Name"]) != key or Version(metadata["Version"]) != version:
            raise ValueError("Wheel metadata does not match the selected distribution.")
        if platform.python_version() not in SpecifierSet(metadata.get("Requires-Python", "")):
            raise ValueError("Wheel metadata requires a different Python version.")
        selected[key] = {
            "name": key,
            "version": str(version),
            "installed": False,
            "kind": "python"
            if all(
                t.abi == "none" and t.platform == "any"
                for t in parse_wheel_filename(file["filename"])[3]
            )
            else "native",
        }
        for dependency in metadata.get_all("Requires-Dist", []):
            await visit(Requirement(dependency))
        wheels[key] = (file["filename"], data)

    await visit(Requirement(name))
    import secrets

    token = secrets.token_hex(16)
    result = {
        "token": token,
        "name": name,
        "packages": list(selected.values()),
        "destination": "Browser Python runtime memory",
        "persistent": False,
    }
    pending = {"result": result, "wheels": wheels, "catalog": catalog_names}
    if pending_store is None:
        _pending = pending
    else:
        pending_store.update(pending)
    return result


async def install_package(token: str) -> dict:
    """Install only the most recently checked plan, consuming it even on failure."""
    global _pending
    if _pending is None or token != _pending["result"]["token"]:
        raise ValueError("Package check expired. Check availability again.")
    plan, _pending = _pending, None
    for package in plan["result"]["packages"]:
        current = _installed(package["name"])
        if current != (package["version"] if package["installed"] else None):
            raise ValueError("Installed packages changed. Check availability again.")
    if plan.get("catalog"):
        from pyodide.ffi import to_js
        from pyodide_js import loadPackage

        await loadPackage(to_js(plan["catalog"]))
        for package in plan["result"]["packages"]:
            if package["name"] in plan["catalog"]:
                _catalog_versions[package["name"]] = package["version"]
    import micropip

    with tempfile.TemporaryDirectory(prefix="flowgraph-packages-") as directory:
        for filename, data in plan["wheels"].values():
            path = Path(directory) / filename
            path.write_bytes(data)
            await micropip.install(f"emfs:{path}", deps=False)
    importlib.invalidate_caches()
    return plan["result"]
