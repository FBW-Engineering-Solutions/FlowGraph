"""Regression coverage for the standalone release gate."""

from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("check_release", ROOT / "packaging/check_release.py")
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


@pytest.fixture
def release_tree(tmp_path: Path) -> Path:
    """Create independent source declarations for a prospective release."""
    (tmp_path / "src/flowgraph").mkdir(parents=True)
    (tmp_path / "packaging/conda").mkdir(parents=True)
    (tmp_path / "dist").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "flowgraph"\nversion = "0.1.5"\n', encoding="utf-8"
    )
    (tmp_path / "src/flowgraph/version.py").write_text('__version__ = "0.1.5"\n', encoding="utf-8")
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "flowgraph"\nversion = "0.1.5"\n', encoding="utf-8"
    )
    (tmp_path / "packaging/conda/meta.yaml").write_text(
        '{% set version = "0.1.5" %}\n', encoding="utf-8"
    )
    write_artifacts(tmp_path / "dist")
    return tmp_path


def write_artifacts(
    directory: Path,
    *,
    filename_version: str = "0.1.5",
    wheel_version: str = "0.1.5",
    sdist_version: str = "0.1.5",
    name: str = "flowgraph",
    wheel_metadata: bool = True,
    sdist_metadata: bool = True,
) -> None:
    """Write tiny archives with independently controllable filename and metadata."""
    with zipfile.ZipFile(
        directory / f"flowgraph-{filename_version}-py3-none-any.whl", "w"
    ) as archive:
        if wheel_metadata:
            archive.writestr(
                f"flowgraph-{filename_version}.dist-info/METADATA",
                f"Name: {name}\nVersion: {wheel_version}\n",
            )
    with tarfile.open(directory / f"flowgraph-{filename_version}.tar.gz", "w:gz") as archive:
        if sdist_metadata:
            data = f"Name: {name}\nVersion: {sdist_version}\n".encode()
            member = tarfile.TarInfo(f"flowgraph-{filename_version}/PKG-INFO")
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))


@pytest.mark.parametrize("tag", [None, "v0.1.5"])
def test_matching_release_passes(release_tree: Path, tag: str | None) -> None:
    assert CHECKER.check_release(release_tree, release_tree / "dist", tag) == "0.1.5"


@pytest.mark.parametrize("tag", ["", "v0.1.2", "v0.1.2.1", "v0.1.3", "v0.1.4", "0.1.5"])
def test_mismatched_tag_fails(release_tree: Path, tag: str) -> None:
    with pytest.raises(ValueError, match="Tag"):
        CHECKER.check_release(release_tree, release_tree / "dist", tag)


@pytest.mark.parametrize(
    "path, message",
    [
        ("src/flowgraph/version.py", "Runtime"),
        ("uv.lock", "Lockfile"),
        ("packaging/conda/meta.yaml", "Conda"),
    ],
)
def test_source_version_drift_fails(release_tree: Path, path: str, message: str) -> None:
    file = release_tree / path
    file.write_text(file.read_text(encoding="utf-8").replace("0.1.5", "0.1.2"), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        CHECKER.check_release(release_tree, release_tree / "dist", "v0.1.5")


@pytest.mark.parametrize(
    "options, message",
    [
        ({"wheel_version": "0.1.2"}, "Version"),
        ({"sdist_version": "0.1.2"}, "Version"),
        ({"name": "other-project"}, "Name"),
        ({"wheel_metadata": False}, "metadata paths"),
        ({"sdist_metadata": False}, "PKG-INFO"),
    ],
)
def test_renamed_or_invalid_artifacts_fail(release_tree: Path, options: dict, message: str) -> None:
    write_artifacts(release_tree / "dist", **options)
    with pytest.raises(ValueError, match=message):
        CHECKER.check_release(release_tree, release_tree / "dist", "v0.1.5")


def test_stale_artifact_pair_fails(release_tree: Path) -> None:
    for file in (release_tree / "dist").iterdir():
        file.unlink()
    write_artifacts(release_tree / "dist", filename_version="0.1.2")
    with pytest.raises(ValueError, match="filename"):
        CHECKER.check_release(release_tree, release_tree / "dist", "v0.1.5")


@pytest.mark.parametrize("kind", ["missing-wheel", "missing-sdist", "extra-wheel", "extra-sdist"])
def test_incomplete_or_mixed_artifact_sets_fail(release_tree: Path, kind: str) -> None:
    directory = release_tree / "dist"
    suffix = "*.whl" if kind.endswith("wheel") else "*.tar.gz"
    file = next(directory.glob(suffix))
    if kind.startswith("missing"):
        file.unlink()
    else:
        (directory / file.name.replace("0.1.5", "0.1.2")).write_bytes(file.read_bytes())
    with pytest.raises(ValueError, match="exactly one"):
        CHECKER.check_release(release_tree, directory, "v0.1.5")


def test_cli_reports_failure_without_traceback(release_tree: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "packaging/check_release.py"),
            "--root",
            str(release_tree),
            "--artifacts",
            str(release_tree / "dist"),
            "--tag",
            "v0.1.4",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "Release validation failed: Tag" in result.stderr
    assert "Traceback" not in result.stderr


def test_publication_jobs_depend_on_release_gate() -> None:
    """Keep both remote publication paths downstream of the same artifact gate."""
    workflow = (ROOT / ".github/workflows/build-packages.yml").read_text(encoding="utf-8")
    for job in ("release", "publish-pypi"):
        body = workflow.split(f"\n  {job}:\n", 1)[1].split("\n  publish-pypi:", 1)[0]
        assert "needs: validate-release" in body
    gate = workflow.split("\n  validate-release:\n", 1)[1].split("\n  release:\n", 1)[0]
    assert 'check_release.py --artifacts release-assets --tag "$GITHUB_REF_NAME"' in gate
    assert "name: flowgraph-core-packages" in gate
    assert "needs: [build, test-artifacts]" in gate
    for job in ("validate-release", "release", "publish-pypi"):
        body = workflow.split(f"\n  {job}:\n", 1)[1].split("\n\n  ", 1)[0]
        assert "if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')" in body


def test_branch_and_pr_runs_include_packaging_matrix() -> None:
    workflow = (ROOT / ".github/workflows/build-packages.yml").read_text(encoding="utf-8")
    assert 'branches: ["**"]' in workflow
    build = workflow.split("\n  build:\n", 1)[1].split("\n  test-artifacts:\n", 1)[0]
    assert "if:" not in build
    assert "uv build --no-sources" in build
    artifacts = workflow.split("\n  test-artifacts:\n", 1)[1].split("\n  validate-release:\n", 1)[0]
    assert "needs: build" in artifacts
    assert "artifact: [wheel, sdist]" in artifacts
    assert 'python-version: ["3.11", "3.12", "3.13", "3.14"]' in artifacts
    assert "os: [ubuntu-latest, windows-latest, macos-latest]" in artifacts
    assert "name: flowgraph-core-packages" in artifacts
    assert "python packaging/test_artifact.py" in artifacts


@pytest.mark.parametrize("job", ["test", "test-artifacts"])
def test_ci_matrix_covers_supported_python_versions(job: str) -> None:
    workflow = (ROOT / ".github/workflows/build-packages.yml").read_text(encoding="utf-8")
    body = workflow.split(f"\n  {job}:\n", 1)[1].split("\n\n  ", 1)[0]
    assert 'python-version: ["3.11", "3.12", "3.13", "3.14"]' in body
    assert "os: [ubuntu-latest, windows-latest, macos-latest]" in body


def artifact_runner():
    spec = importlib.util.spec_from_file_location(
        "artifact_runner", ROOT / "packaging/test_artifact.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("kind, suffix", [("wheel", ".whl"), ("sdist", ".tar.gz")])
def test_artifact_runner_uses_clean_environment_and_exact_archive(
    tmp_path: Path, monkeypatch, kind: str, suffix: str
) -> None:
    runner = artifact_runner()
    archive = tmp_path / f"flowgraph-0.1.5{suffix}"
    archive.touch()
    calls = []
    monkeypatch.setenv("PYTHONPATH", str(ROOT / "src"))
    monkeypatch.setenv("VIRTUAL_ENV", str(ROOT / ".venv"))
    monkeypatch.setattr(runner.shutil, "which", lambda _: "/fake/uv")

    def record(command, *, cwd, env, check):
        assert check
        assert not cwd.resolve().is_relative_to(ROOT)
        assert "PYTHONPATH" not in env
        assert "VIRTUAL_ENV" not in env
        calls.append(command)

    monkeypatch.setattr(runner.subprocess, "run", record)
    runner.test_artifact(tmp_path, kind, ROOT)
    assert calls[0][1] == "venv"
    assert calls[1][-1] == str(archive)
    assert "--no-deps" not in calls[1]
    assert calls[2][1:3] == ["pip", "check"]
    assert calls[3][1] == "-I"
    assert Path(calls[3][2]).name == "smoke_installed.py"


@pytest.mark.parametrize("count", [0, 2])
def test_artifact_runner_rejects_missing_or_ambiguous_archives(tmp_path: Path, count: int) -> None:
    for index in range(count):
        (tmp_path / f"flowgraph-{index}.whl").touch()
    with pytest.raises(ValueError, match="exactly one"):
        artifact_runner().test_artifact(tmp_path, "wheel", ROOT)
