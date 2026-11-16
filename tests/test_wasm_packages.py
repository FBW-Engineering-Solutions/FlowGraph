"""Package checks do not mutate the runtime; installation consumes a checked plan."""

import asyncio
import hashlib
import io
import sys
import types
import zipfile
from pathlib import Path

import pytest

from flowgraph.application import wasm_packages as packages


@pytest.fixture
def repository(monkeypatch):
    projects, downloads, requests, installs = {}, {}, [], []
    installed = {}
    monkeypatch.setattr(packages, "_pending", None)
    monkeypatch.setattr(packages, "_installed", installed.get)

    async def fetch(url, *, binary=False):
        requests.append(url)
        return downloads[url] if binary else projects[url.split("/")[-2]]

    async def install(url, **kwargs):
        assert kwargs == {"deps": False}
        path = Path(url.removeprefix("emfs:"))
        assert path.is_file()
        installs.append(path.name)

    monkeypatch.setattr(packages, "_fetch", fetch)
    monkeypatch.setitem(sys.modules, "micropip", types.SimpleNamespace(install=install))

    def add(name, version="1.0", dependencies=(), *, tag="py3-none-any", python="", yanked=False):
        filename = f"{name}-{version}-{tag}.whl"
        metadata = f"Name: {name}\nVersion: {version}\nRequires-Python: {python}\n"
        metadata += "".join(f"Requires-Dist: {dependency}\n" for dependency in dependencies)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(f"{name}-{version}.dist-info/METADATA", metadata)
        data = buffer.getvalue()
        url = f"https://files.pythonhosted.org/{filename}"
        downloads[url] = data
        projects.setdefault(name, {"releases": {}})["releases"][version] = [
            {
                "filename": filename,
                "url": url,
                "digests": {"sha256": hashlib.sha256(data).hexdigest()},
                "size": len(data),
                "packagetype": "bdist_wheel",
                "requires_python": python,
                "yanked": yanked,
            }
        ]
        return url

    return types.SimpleNamespace(
        add=add,
        installed=installed,
        installs=installs,
        requests=requests,
        downloads=downloads,
        projects=projects,
    )


def test_check_then_install_exact_bytes_and_consume_token(repository):
    repository.add("example", dependencies=("dependency>=1", "native; sys_platform == 'never'"))
    repository.add("dependency")
    plan = asyncio.run(packages.check_package("example"))
    assert [p["name"] for p in plan["packages"]] == ["example", "dependency"]
    assert not repository.installs
    before = len(repository.requests)
    assert asyncio.run(packages.install_package(plan["token"])) == plan
    assert repository.installs == [
        "dependency-1.0-py3-none-any.whl",
        "example-1.0-py3-none-any.whl",
    ]
    assert len(repository.requests) == before
    with pytest.raises(ValueError, match="expired"):
        asyncio.run(packages.install_package(plan["token"]))


@pytest.mark.parametrize("name", ["https://example.com/a.whl", "foo==1", "foo[extra]", "", "a b"])
def test_reject_non_names(repository, name):
    with pytest.raises(ValueError, match="package name"):
        asyncio.run(packages.check_package(name))
    assert not repository.requests


@pytest.mark.parametrize(
    "options",
    [
        {"tag": "cp313-cp313-manylinux_2_17_x86_64"},
        {"python": ">=99"},
        {"yanked": True},
    ],
)
def test_reject_incompatible_wheels(repository, options):
    repository.add("example", **options)
    with pytest.raises(ValueError, match="No compatible pure-Python or WebAssembly wheel"):
        asyncio.run(packages.check_package("example"))
    assert not repository.installs


def test_dependency_conflicts_and_existing_native_packages(repository):
    repository.add("example", dependencies=("native>=2",))
    repository.installed["native"] = "2.0"
    plan = asyncio.run(packages.check_package("example"))
    assert plan["packages"][1]["installed"]
    repository.installed["native"] = "1.0"
    with pytest.raises(ValueError, match="conflicts with installed"):
        asyncio.run(packages.check_package("example"))
    with pytest.raises(ValueError, match="expired"):
        asyncio.run(packages.install_package(plan["token"]))


def test_integrity_failure_and_changed_environment(repository):
    url = repository.add("example")
    plan = asyncio.run(packages.check_package("example"))
    repository.installed["example"] = "2.0"
    with pytest.raises(ValueError, match="changed"):
        asyncio.run(packages.install_package(plan["token"]))
    repository.installed.clear()
    repository.downloads[url] = b"tampered"
    with pytest.raises(ValueError, match="integrity"):
        asyncio.run(packages.check_package("example"))


def test_dependencies_without_pure_wheels_block_check(repository):
    repository.add("example", dependencies=("native",))
    repository.add("native", tag="cp313-cp313-manylinux_2_17_x86_64")
    with pytest.raises(ValueError, match="native"):
        asyncio.run(packages.check_package("example"))
    assert not repository.installs


def test_dependency_constraints_and_cycles(repository):
    repository.add("example", dependencies=("left", "right"))
    repository.add("left", dependencies=("shared<2", "example"))
    repository.add("right", dependencies=("shared>=2",))
    repository.add("shared")
    repository.add("shared", "2.0")
    with pytest.raises(ValueError, match="Conflicting dependency"):
        asyncio.run(packages.check_package("example"))
    assert not repository.installs
