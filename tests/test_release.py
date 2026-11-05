"""Regression coverage for the standalone release gate."""

from __future__ import annotations

import importlib.util
import io
import os
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


def test_release_docs_use_planned_mvp_baseline_without_missing_audit() -> None:
    """Keep the MVP scope explicit without depending on a missing pre-MVP audit."""
    packaging = (ROOT / "packaging/README.md").read_text(encoding="utf-8")
    policy = (ROOT / "docs/policies/release-policy.md").read_text(encoding="utf-8")
    changelog = (ROOT / "docs/changelog.md").read_text(encoding="utf-8")
    for document in (packaging, policy, changelog):
        document = " ".join(document.split())
        assert "release-reconciliation.md" not in document
        assert "planned first mvp baseline" in document.lower()
        assert "not a publication announcement" in document
        assert "stable API commitment" in document
    for document in (packaging, policy):
        assert "`0.1.8`" in document
        assert "Pre-MVP releases are outside this release-readiness" in document
        assert "packaging/check_release.py" in document
    assert "New in version 0.1.7:" in changelog
    assert "New in version 0.1.5:" in changelog


def test_security_reporting_docs_keep_unverified_delivery_explicit() -> None:
    security = " ".join((ROOT / "SECURITY.md").read_text(encoding="utf-8").split())
    assert "GitHub private vulnerability reporting" in security
    assert "Report-delivery verification remains an open maintainer task" in security
    assert "no verified fallback private contact route is documented here" in security
    assert "without including vulnerability details" in security
    assert "seven calendar days" in security
    assert "no guaranteed response or remediation timeframe" in security
    assert "Before the repository is made public" not in security


@pytest.mark.parametrize(
    "path",
    ["docs/maintainers/governance.md", "docs/policies/release-policy.md", "packaging/README.md"],
)
def test_release_guidance_is_self_contained_and_keeps_applicable_checks(path: str) -> None:
    document = " ".join((ROOT / path).read_text(encoding="utf-8").split())
    assert "optional improvements" in document.lower()
    assert "relevant unresolved" in document
    assert "reviewed and recorded" in document or "Review and record" in document
    assert "after the release checklist is satisfied" not in document
    assert "todo.md" not in document.lower()


def test_support_docs_keep_platform_and_client_validation_separate() -> None:
    support = " ".join(
        (ROOT / "docs/policies/support-policy.md").read_text(encoding="utf-8").split()
    )
    assert "Windows, macOS, or unverified Linux architectures as supported platforms" not in support
    assert "without passing release-candidate evidence" in support
    assert "corresponding matrix jobs pass for the release candidate" in support
    for path in (
        "docs/policies/support-policy.md",
        "docs/policies/release-channels.md",
        ".github/SUPPORT.md",
    ):
        document = " ".join((ROOT / path).read_text(encoding="utf-8").split())
        assert "Desktop" in document and "Web" in document
        assert "Initial public FlowGraph Core release" not in document


@pytest.fixture
def release_tree(tmp_path: Path) -> Path:
    """Create independent source declarations for a prospective release."""
    (tmp_path / "src/flowgraph").mkdir(parents=True)
    (tmp_path / "dist").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "flowgraph"\nversion = "0.1.5"\n', encoding="utf-8"
    )
    (tmp_path / "src/flowgraph/version.py").write_text('__version__ = "0.1.5"\n', encoding="utf-8")
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "flowgraph"\nversion = "0.1.5"\n', encoding="utf-8"
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


def test_core_ci_gate_runs_after_all_prerequisites_even_on_failure() -> None:
    workflow = (ROOT / ".github/workflows/build-packages.yml").read_text(encoding="utf-8")
    gate = workflow.split("\n  core-ci:\n", 1)[1].split("\n  validate-release:\n", 1)[0]
    assert "name: Core CI\n" in gate
    assert "if: always()\n" in gate
    assert "needs: [test, build, test-artifacts]\n" in gate
    assert "shell: bash\n" in gate
    for variable, job in (
        ("SOURCE_RESULT", "test"),
        ("BUILD_RESULT", "build"),
        ("ARTIFACT_RESULT", "test-artifacts"),
    ):
        assert f"{variable}: ${{{{ needs.{job}.result }}}}" in gate
    assert "uses:" not in gate
    assert "continue-on-error:" not in workflow


@pytest.mark.parametrize("result", ["success", "failure", "cancelled", "skipped", ""])
@pytest.mark.parametrize("variable", ["SOURCE_RESULT", "BUILD_RESULT", "ARTIFACT_RESULT"])
def test_core_ci_shell_rejects_every_unsuccessful_prerequisite(variable: str, result: str) -> None:
    workflow = (ROOT / ".github/workflows/build-packages.yml").read_text(encoding="utf-8")
    gate = workflow.split("\n  core-ci:\n", 1)[1].split("\n  validate-release:\n", 1)[0]
    script = gate.split("        run: |\n", 1)[1]
    script = "\n".join(line.removeprefix("          ") for line in script.splitlines())
    env = dict(
        os.environ, SOURCE_RESULT="success", BUILD_RESULT="success", ARTIFACT_RESULT="success"
    )
    env[variable] = result
    completed = subprocess.run(
        ["bash", "-c", script], env=env, capture_output=True, text=True, check=False
    )
    assert completed.returncode == (0 if result == "success" else 1)
    if result != "success":
        assert f"observed: {result}" in completed.stdout


def test_pr_workflow_keeps_publication_permissions_in_tag_only_jobs() -> None:
    workflow = (ROOT / ".github/workflows/build-packages.yml").read_text(encoding="utf-8")
    assert "  pull_request:\n" in workflow
    assert "pull_request_target" not in workflow
    assert "permissions:\n  contents: read\n" in workflow
    assert "secrets." not in workflow
    for job in ("test", "build", "test-artifacts", "core-ci", "validate-release"):
        body = workflow.split(f"\n  {job}:\n", 1)[1].split("\n\n  ", 1)[0]
        assert "permissions:" not in body
        assert "environment:" not in body
    for job, permission in (("release", "contents: write"), ("publish-pypi", "id-token: write")):
        body = workflow.split(f"\n  {job}:\n", 1)[1].split("\n\n  ", 1)[0]
        assert "if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')" in body
        assert permission in body
        assert workflow.count(permission) == 1


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
