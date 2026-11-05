"""Tests for GUI-free FlowGraph core package metadata."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

from flowgraph.adapters import ADAPTERS
from flowgraph.version import __version__


def test_website_documents_every_registered_adapter_node() -> None:
    """Catch missing node IDs and adapter families in the website reference."""
    root = Path(__file__).parents[1]
    reference = root / "doc" / "reference" / "adapters"
    pages = {
        "Scalars": "inputs.md",
        "Lists/Vectors": "inputs.md",
        "Files": "file.md",
        "Readers": "readers.md",
        "Mesh Creation": "mesh-creation-tools.md",
        "Filters": "filters.md",
        "Mesh Ops": "mesh-ops.md",
        "Field Ops": "field-ops.md",
        "File Conversion": "file-conversion.md",
        "Writers": "writers.md",
        "Controls": "controls.md",
        "Image Tools": "image-tools.md",
        "Table Tools": "table-tools.md",
        "Vector Tools": "vector-tools.md",
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
                    if definition.subworkflows_factory is not None
                    else markdown
                )
                if f"`{definition.id}`" not in content:
                    missing.append((subgroup.label, definition.id, page.name))
    assert not missing, f"Undocumented adapter nodes: {missing}"


def test_custom_node_guide_example_executes(tmp_path: Path) -> None:
    """Keep the public Python node recipe executable, including its JSON round trip."""
    root = Path(__file__).parents[1]
    guide = (root / "doc" / "user-guide" / "custom-nodes.md").read_text(encoding="utf-8")
    examples = [part.split("\n```", 1)[0] for part in guide.split("```python\n")[1:]]
    script = "\n".join(examples)
    completed = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, capture_output=True, text=True, check=True
    )
    assert completed.stdout.strip() == "21"
    assert (tmp_path / "scaled-workflow.json").is_file()
    catalog = json.loads((tmp_path / "node-catalog.json").read_text(encoding="utf-8"))
    assert catalog["groups"][-1]["label"] == "My Nodes"
    assert catalog["groups"][-1]["nodes"][0]["id"] == "scale-integer"


def test_custom_node_guide_is_in_site_navigation() -> None:
    root = Path(__file__).parents[1]
    nav = tomllib.loads((root / "zensical.toml").read_text(encoding="utf-8"))["project"]["nav"]
    guide_nav = next(entry["User Guide"] for entry in nav if "User Guide" in entry)
    assert any("user-guide/custom-nodes.md" in item.values() for item in guide_nav)


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


def test_public_metadata_links_to_documentation() -> None:
    """Publish the same documentation destination as the public README."""
    root = Path(__file__).parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    documentation = project["urls"]["Documentation"]

    assert documentation == "https://flowgraph.readthedocs.io/en/latest/"
    assert f"[FlowGraph documentation]({documentation})" in (root / "README.md").read_text(
        encoding="utf-8"
    )


def test_python_classifiers_match_ci_support_targets() -> None:
    """Keep version-specific classifiers aligned with test and artifact matrices."""
    root = Path(__file__).parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    prefix = "Programming Language :: Python :: "
    versions = {
        classifier.removeprefix(prefix)
        for classifier in project["classifiers"]
        if classifier.startswith(prefix) and classifier.removeprefix(prefix).count(".") == 1
    }
    assert versions == {"3.11", "3.12", "3.13", "3.14"}
    assert project["requires-python"] == ">=3.11"

    workflow = (root / ".github" / "workflows" / "build-packages.yml").read_text(encoding="utf-8")
    matrices = re.findall(r"^\s+python-version: (\[.*\])$", workflow, re.MULTILINE)
    assert len(matrices) == 2
    for matrix in matrices:
        assert set(tomllib.loads(f"versions = {matrix}")["versions"]) == versions


def test_third_party_notices_describe_open_source_core() -> None:
    """Keep the notices scoped to the Core license rather than the retired product."""
    root = Path(__file__).parents[1]
    notices = (root / "doc" / "reference" / "third-party-notices.md").read_text(encoding="utf-8")
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert f"FlowGraph Core is licensed under **{project['license']}**" in notices
    assert "proprietary" not in notices.lower()
    assert "id: reference.third-party-notices\n" in notices


def test_third_party_notice_inventory_matches_declared_dependencies() -> None:
    """Check direct dependency groups and snapshot versions without network access."""
    root = Path(__file__).parents[1]
    notices = (root / "doc" / "reference" / "third-party-notices.md").read_text(encoding="utf-8")
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    versions = {}
    for package in lock["package"]:
        versions.setdefault(package["name"], set()).add(package["version"])
    groups = {"required": project["dependencies"], **project["optional-dependencies"]}
    expected = set()
    for group, dependencies in groups.items():
        for dependency in dependencies:
            match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", dependency)
            assert match is not None, dependency
            name = re.sub(r"[-_.]+", "-", match.group()).lower()
            expected.add((name, group))

    rows = re.findall(r"^\| `([^`]+)` \| `([^`]+)` \| `([^`]+)` \|", notices, re.MULTILINE)
    actual = {(name, group) for name, group, _ in rows}
    assert len(rows) == len(actual), "Duplicate dependency/group rows"
    assert actual == expected
    for name, _, version in rows:
        assert version in versions[name], f"Stale locked version for {name}: {version}"


def test_installation_guide_matches_python_requirement_and_runtime_extras() -> None:
    """Keep installation guidance aligned with metadata, not retired binary releases."""
    root = Path(__file__).parents[1]
    guide = (root / "doc" / "getting-started" / "installation.md").read_text(encoding="utf-8")
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    minimum = project["requires-python"].removeprefix(">=")
    assert f"Python {minimum} or newer" in guide
    assert f'requires-python = "{project["requires-python"]}"' in guide
    assert "pure-Python wheel" in guide
    for retired in ["Python 3.10", "binary wheel", "binary package", "authoring-only"]:
        assert retired not in guide
    documented_extras = set(re.findall(r"^\| `([^`]+)` \|", guide, re.MULTILINE))
    assert documented_extras == set(project["optional-dependencies"]) - {"dev", "ci"}
    for spec in re.findall(r"flowgraph\[([^]]+)\]", guide):
        assert set(spec.split(",")) <= documented_extras


def test_installation_guide_cli_examples_execute(tmp_path: Path) -> None:
    """Exercise the actual documented persistent CLI arguments without installing tools."""
    from flowgraph.adapters.simple_sources import SET_STRING
    from flowgraph.adapters.workflow_interfaces import WORKFLOW_OUTPUT
    from flowgraph.application.node_registry import create_node_registry
    from flowgraph.application.workflow_core import WorkflowEdge, WorkflowGraph
    from flowgraph.application.workflow_io import save_workflow

    registry = create_node_registry()
    graph = WorkflowGraph()
    for node_id, value, output_name in [
        ("text_source", "saved-text", "text"),
        ("label_source", "saved-label", "label"),
        ("source", "saved-source", "result"),
    ]:
        graph.add_node(SET_STRING.create_instance(node_id, parameters={"value": value}))
        target = f"{node_id}_output"
        graph.add_node(WORKFLOW_OUTPUT.create_instance(target, parameters={"name": output_name}))
        graph.add_edge(WorkflowEdge(node_id, "value", target, "value"), registry)
    graph.sync_boundary_nodes(registry)
    graph.export_input("text", "text_source", "value", registry)
    graph.export_input("label", "label_source", "value", registry)
    workflow = save_workflow(graph, tmp_path / "workflow.json")
    original = workflow.read_bytes()
    guide = (Path(__file__).parents[1] / "doc" / "getting-started" / "installation.md").read_text(
        encoding="utf-8"
    )
    commands = re.findall(r"^uv run --no-project flowgraph (.+)$", guide, re.MULTILINE)
    assert len(commands) == 4
    for command in commands:
        completed = subprocess.run(
            [sys.executable, "-m", "flowgraph.core_cli", *shlex.split(command)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        if command == "--help":
            assert "inspect" in completed.stdout and "run" in completed.stdout
        elif command.startswith("inspect "):
            assert "text" in completed.stdout and "label" in completed.stdout
        elif "--json-output" in command:
            assert json.loads((tmp_path / "outputs.json").read_text(encoding="utf-8")) == {
                "text": "hello",
                "label": "example",
                "result": "updated",
            }
        else:
            assert all(
                value in completed.stdout for value in ["saved-text", "saved-label", "saved-source"]
            )
            assert "warning" in completed.stderr.lower()
    assert workflow.read_bytes() == original


def test_io_dependencies_are_optional() -> None:
    """Keep I/O libraries opt-in with the same constraints in the lockfile."""
    root = Path(__file__).parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    expected = [
        "meshio>=5.3",
        "meshlane>=5.5.0",
        "pandas",
        "h5py",
        "pillow>=10.0",
        "openpyxl>=3.1.5",
    ]
    assert project["optional-dependencies"]["io"] == expected
    names = {dependency.split(">", 1)[0] for dependency in expected}
    assert names.isdisjoint(dependency.split(">", 1)[0] for dependency in project["dependencies"])

    requirements = {
        line
        for line in (root / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }
    assert requirements == set(project["dependencies"])

    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    package = next(package for package in lock["package"] if package["name"] == "flowgraph")
    assert {dependency["name"] for dependency in package["optional-dependencies"]["io"]} == names
    assert names.isdisjoint(dependency["name"] for dependency in package["dependencies"])


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


def test_packaging_configuration_has_no_machine_specific_paths() -> None:
    """Check comments too, since TOML parsing would discard local build notes."""
    root = Path(__file__).parents[1]
    for path in (root / "pyproject.toml", root / "packaging/README.md"):
        text = path.read_text(encoding="utf-8")
        assert re.search(r"/(?:home|Users)/|(?<![A-Za-z])[A-Za-z]:[\\/]", text) is None


def test_packaging_rehearsal_commands_use_consistent_relative_output() -> None:
    """Keep portable examples aligned with the artifact runner's CLI contract."""
    root = Path(__file__).parents[1]
    guide = (root / "packaging/README.md").read_text(encoding="utf-8")
    section = guide.split("Run the same checks locally from the repository root:", 1)[1]
    block = section.split("```bash\n", 1)[1].split("\n```", 1)[0]
    build, wheel, sdist = [shlex.split(line) for line in block.splitlines()]
    assert build[:4] == ["uv", "build", "--no-sources", "--out-dir"]
    output = build[4]
    assert Path(output).parts[0] == ".validation-dist"
    assert not Path(output).is_absolute()
    assert ".validation-dist/" in (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    for command, kind in ((wheel, "wheel"), (sdist, "sdist")):
        assert command == [
            "uv",
            "run",
            "python",
            "packaging/test_artifact.py",
            "--artifacts",
            output,
            "--kind",
            kind,
        ]
        completed = subprocess.run(
            [sys.executable, str(root / command[3]), "--help"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert "--artifacts" in completed.stdout
        assert "--kind {wheel,sdist}" in completed.stdout
    assert "new, empty output directory per rehearsal" in section
    assert "environments outside the checkout" in section


def test_conda_recipe_is_absent() -> None:
    """Keep the retired Conda recipe out of the packaging workflow."""
    root = Path(__file__).parents[1]
    assert not (root / "packaging" / "conda" / "meta.yaml").exists()


def test_release_version_is_consistent() -> None:
    """Keep the runtime, lockfile, and release notes in sync with package metadata."""
    root = Path(__file__).parents[1]
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    local_package = next(package for package in lock["package"] if package["name"] == "flowgraph")

    assert __version__ == version
    assert local_package["version"] == version
    assert f"New in version {version}:" in (root / "docs" / "changelog.md").read_text(
        encoding="utf-8"
    )
