"""Tests for GUI-free FlowGraph core package metadata."""

from __future__ import annotations

import tomllib
from pathlib import Path


def test_core_metadata_excludes_desktop_dependencies_and_entry_points() -> None:
    """Keep GUI dependencies out of the core distribution and publish BSD metadata."""
    metadata = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    project = metadata["project"]
    dependencies = project["dependencies"]

    assert project["scripts"] == {"flowgraph": "flowgraph.core_cli:main"}
    assert project["license"] == "BSD-3-Clause"
    assert project["license-files"] == ["LICENSE"]
    assert project["authors"] == [{"name": "Felipe Bordeu"}]
    assert project["maintainers"] == [{"name": "Felipe Bordeu"}]
    assert project["keywords"]
    assert "Development Status :: 3 - Alpha" in project["classifiers"]
    assert all(
        not dependency.startswith(
            ("trame", "markdown-it-py", "pywebview", "pygobject", "cryptography")
        )
        for dependency in dependencies
    )
    assert "vtk>=9.2" in dependencies


def test_core_package_uses_standard_pure_python_build_configuration() -> None:
    """Require setuptools packaging without a Cython build dependency."""
    root = Path(__file__).parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["build-system"] == {
        "requires": ["setuptools>=68"],
        "build-backend": "setuptools.build_meta",
    }
    assert all(
        "cython" not in dependency.lower()
        for dependency in metadata["project"]["optional-dependencies"]["dev"]
    )


def test_legacy_cython_packaging_files_are_absent() -> None:
    """Prevent reintroducing the retired native-extension build pipeline."""
    packaging_directory = Path(__file__).parents[1] / "packaging"

    assert not (packaging_directory / "setup_core_cython.py").exists()
    assert not (packaging_directory / "build_core_wheel.py").exists()
    assert not (packaging_directory / "build_core_release.py").exists()
    assert not (packaging_directory / "pyproject.toml").exists()
