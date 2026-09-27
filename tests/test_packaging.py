"""Tests for GUI-free FlowGraph core package metadata."""

from __future__ import annotations

import tomllib
from pathlib import Path

from flowgraph.adapters import ADAPTERS


def test_website_documents_every_registered_adapter_node() -> None:
    """Catch missing node IDs and adapter families in the website reference."""
    root = Path(__file__).parents[1]
    reference = root / "doc" / "reference" / "adapters"
    pages = {
        "Scalars": "inputs.md",
        "Lists/Vectors": "inputs.md",
        "Files": "file.md",
        "Readers": "readers.md",
        "Mesh Gens": "mesh-gens.md",
        "Mesh Creation": "mesh-creation-tools.md",
        "Filters": "filters.md",
        "Mesh Ops": "mesh-ops.md",
        "Field Ops": "field-ops.md",
        "File Conversion": "file-conversion.md",
        "Writers": "writers.md",
        "Controls": "controls.md",
        "Image Tools": "image-tools.md",
        "Table Tools": "table-tools.md",
        "Code": "code.md",
        "Workflow": "workflow.md",
        "Sinks": "sinks.md",
        "Doc": "doc.md",
        "CoSApp": "cosapp.md",
        "Plaid": "plaid.md",
    }
    nav = tomllib.loads((root / "zensical.toml").read_text(encoding="utf-8"))
    reference_nav = next(
        entry["Reference"] for entry in nav["project"]["nav"] if "Reference" in entry
    )
    linked_pages = {path for entry in reference_nav for path in entry.values()}
    assert all(f"reference/adapters/{page}" in linked_pages for page in pages.values())

    missing = []
    for group in ADAPTERS.groups:
        for subgroup in group.subgroups or (group,):
            page = reference / pages[subgroup.label]
            markdown = page.read_text(encoding="utf-8")
            for definition in subgroup.node_definitions:
                # Composite workflow nodes are explained alongside their controls.
                content = (
                    (reference / "controls.md").read_text(encoding="utf-8")
                    if definition.subworkflow_factory is not None
                    else markdown
                )
                if f"`{definition.id}`" not in content:
                    missing.append((subgroup.label, definition.id, page.name))
    assert not missing, f"Undocumented adapter nodes: {missing}"


def test_website_documentation_is_not_packaged_by_core() -> None:
    """Keep the website source under doc/ and out of the Python distribution."""
    root = Path(__file__).parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = metadata["tool"]["setuptools"]["package-data"]["flowgraph"]

    assert not any("documentation" in pattern for pattern in package_data)
    assert not (root / "src" / "flowgraph" / "documentation_content").exists()
    site = tomllib.loads((root / "zensical.toml").read_text(encoding="utf-8"))
    assert root / site["project"]["docs_dir"] == root / "doc"
    assert (root / "doc" / "index.md").is_file()


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


def test_conda_recipe_tracks_the_published_python_package() -> None:
    """Keep the Conda recipe aligned with the release metadata and CLI."""
    root = Path(__file__).parents[1]
    recipe = (root / "packaging" / "conda" / "meta.yaml").read_text(encoding="utf-8")
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]

    assert f'{{% set name = "{project["name"]}" %}}' in recipe
    assert f'{{% set version = "{project["version"]}" %}}' in recipe
    assert "noarch: python" in recipe
    assert "--no-deps --no-build-isolation" in recipe
    assert "- flowgraph --help" in recipe
    assert "- flowgraph" in recipe
    assert "license: BSD-3-Clause" in recipe
    for dependency in project["dependencies"]:
        package_name = dependency.split(">", 1)[0].split("=", 1)[0].strip()
        assert f"- {package_name}" in recipe
