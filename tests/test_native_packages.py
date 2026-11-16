"""Workspace packages remain isolated, persistent, opt-in, and wheel-only."""

import asyncio
import base64
import csv
import hashlib
import io
import subprocess
import sys
import zipfile

import pytest
from packaging.tags import sys_tags

from flowgraph.application import wasm_packages
from flowgraph.server.packages import PackageManager, checked_directory
from flowgraph.server.workspace import Workspace


def repository(
    manager, *, tag="py3-none-any", module="fg_extra_test", name="fg-extra-test", dependencies=()
):
    filename = f"{name.replace('-', '_')}-1.0-{tag}.whl"
    prefix = f"{name.replace('-', '_')}-1.0.dist-info"
    entries = {
        f"{module}/__init__.py": b"VALUE = 42\n",
        f"{prefix}/METADATA": (
            f"Metadata-Version: 2.1\nName: {name}\nVersion: 1.0\n"
            + "".join(f"Requires-Dist: {item}\n" for item in dependencies)
        ).encode(),
        f"{prefix}/WHEEL": f"Wheel-Version: 1.0\nGenerator: FlowGraph-test\nRoot-Is-Purelib: true\nTag: {tag}\n".encode(),
    }
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    for path, data in entries.items():
        writer.writerow(
            [
                path,
                "sha256="
                + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("="),
                len(data),
            ]
        )
    writer.writerow([f"{prefix}/RECORD", "", ""])
    entries[f"{prefix}/RECORD"] = output.getvalue().encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for path, data in entries.items():
            archive.writestr(path, data)
    data = stream.getvalue()
    requests = []

    async def fetch(url, *, binary=False):
        requests.append(url)
        if binary:
            return data
        return {
            "releases": {
                "1.0": [
                    {
                        "filename": filename,
                        "packagetype": "bdist_wheel",
                        "url": f"https://files.pythonhosted.org/{filename}",
                        "size": len(data),
                        "digests": {"sha256": hashlib.sha256(data).hexdigest()},
                    }
                ]
            }
        }

    manager.fetch = fetch
    return requests


def test_native_install_exact_bytes_persists_and_imports(tmp_path):
    pytest.importorskip("uv")
    manager = PackageManager(tmp_path, enabled=True)
    requests = repository(manager, tag=str(next(sys_tags())))
    plan = manager.check("fg-extra-test")
    assert plan["persistent"] and plan["packages"][0]["kind"] == "native"
    assert not checked_directory(tmp_path).exists()
    before = len(requests)
    manager.install(plan["token"])
    assert len(requests) == before  # confirmation never re-resolves or downloads
    restarted = PackageManager(tmp_path, enabled=True)
    assert restarted.installed("fg-extra-test") == "1.0"
    target = checked_directory(tmp_path)
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.path.append({str(target)!r}); import fg_extra_test; print(fg_extra_test.VALUE)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert process.stdout.strip() == "42"
    assert not Workspace(tmp_path).listing()["files"]
    with pytest.raises(ValueError, match="expired"):
        manager.install(plan["token"])
    # Removing only this workspace folder uninstalls extras.
    import shutil

    shutil.rmtree(tmp_path / ".flowgraph-packages")
    assert restarted.installed("fg-extra-test") is None


def test_permissions_and_symlinks(tmp_path):
    disabled = PackageManager(tmp_path)
    assert not disabled.info()["enabled"]
    with pytest.raises(PermissionError, match="allow-package-install"):
        disabled.check("fg-extra-test")
    tmp_path.chmod(0o555)
    try:
        enabled = PackageManager(tmp_path, enabled=True)
        assert not enabled.info()["enabled"]
        with pytest.raises(PermissionError, match="read-only"):
            enabled.check("fg-extra-test")
    finally:
        tmp_path.chmod(0o755)
    (tmp_path / ".flowgraph-packages").symlink_to(tmp_path)
    with pytest.raises(PermissionError, match="symbolic link"):
        enabled.info()


def test_preserve_installed_conflicts_and_shadowing(tmp_path):
    pytest.importorskip("uv")
    manager = PackageManager(tmp_path, enabled=True)
    repository(manager, dependencies=("packaging>=99999",))
    with pytest.raises(ValueError, match="conflicts with installed"):
        manager.check("fg-extra-test")
    repository(manager, module="json")
    plan = manager.check("fg-extra-test")
    with pytest.raises(ValueError, match="shadow existing Python module: json"):
        manager.install(plan["token"])
    assert not checked_directory(tmp_path).exists()


def test_invalid_input_and_no_source_builds(tmp_path):
    manager = PackageManager(tmp_path, enabled=True)
    for name in (None, "thing>=1", "thing[extra]", "https://example.com/a.whl"):
        with pytest.raises(ValueError, match="name only"):
            manager.check(name)
    repository(manager, tag="cp999-cp999-win_amd64")
    with pytest.raises(ValueError, match="No compatible native"):
        manager.check("fg-extra-test")


def test_catalog_integrity_dependencies_and_pin(monkeypatch):
    monkeypatch.setattr(wasm_packages, "_installed", lambda name: None)
    data = b"checked wasm artifact"
    entry = {
        "version": "1.0",
        "file_name": "https://cdn.jsdelivr.net/pyodide/v0.29.4/full/example.whl",
        "sha256": hashlib.sha256(data).hexdigest(),
        "depends": ["helper"],
    }
    catalog = {"example": entry, "helper": {**entry, "depends": []}}
    calls = []

    async def fetch(url, *, binary=False):
        calls.append(url)
        assert binary
        return data

    plan = asyncio.run(wasm_packages.check_package("example", catalog=catalog, fetcher=fetch))
    assert [item["kind"] for item in plan["packages"]] == ["wasm", "wasm"]
    assert wasm_packages._pending["catalog"] == ["helper", "example"]
    assert len(calls) == 2
    catalog["example"]["sha256"] = "bad"
    with pytest.raises(ValueError, match="integrity"):
        asyncio.run(wasm_packages.check_package("example", catalog=catalog, fetcher=fetch))
    assert wasm_packages._pending is None


def test_file_api_cannot_mutate_package_directory(tmp_path):
    workspace = Workspace(tmp_path)
    with pytest.raises(ValueError, match="managed by the package API"):
        workspace.write(".flowgraph-packages/fake.py", b"bad")
