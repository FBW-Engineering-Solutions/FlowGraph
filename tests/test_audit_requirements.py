"""Offline coverage for the CI dependency inventory and its explicit audit target."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "audit_requirements", ROOT / "packaging/audit_requirements.py"
)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def distribution(name: str, version: str) -> SimpleNamespace:
    return SimpleNamespace(metadata={"Name": name}, version=version)


def test_snapshot_normalizes_sorts_and_excludes_only_flowgraph() -> None:
    installed = [
        distribution("Zeta_pkg", "1.0+local"),
        distribution("FlowGraph", "0.1.8"),
        distribution("pip-audit", "2.9.0"),
        distribution("Alpha.Pkg", "2.0rc1"),
        distribution("zeta-pkg", "1.0+local"),
    ]
    expected = (["alpha-pkg==2.0rc1", "pip-audit==2.9.0", "zeta-pkg==1.0+local"], "0.1.8")
    assert AUDIT.snapshot(installed) == expected
    assert AUDIT.snapshot(reversed(installed)) == expected


@pytest.mark.parametrize(
    "installed, message",
    [
        ([], "FlowGraph is not installed"),
        ([distribution("flowgraph", "0.1.8")], "No installed dependencies"),
        ([distribution("bad\nname", "1")], "Invalid installed distribution name"),
        ([distribution("valid", "1\nother==2")], "Invalid installed version"),
        ([distribution("valid", "")], "Invalid installed version"),
        ([distribution("dup_pkg", "1"), distribution("dup-pkg", "2")], "Conflicting"),
    ],
)
def test_snapshot_rejects_incomplete_or_unsafe_inventory(installed, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        AUDIT.snapshot(installed)


def test_snapshot_cli_writes_and_logs_inventory(tmp_path: Path, monkeypatch, capsys) -> None:
    output = tmp_path / "nested/requirements.txt"
    monkeypatch.setattr(sys, "argv", ["audit_requirements.py", "--output", str(output)])
    monkeypatch.setattr(
        AUDIT,
        "distributions",
        lambda: [
            distribution("flowgraph", "0.1.8"),
            distribution("pytest", "8.0"),
        ],
    )
    assert AUDIT.main() == 0
    assert output.read_text() == "pytest==8.0\n"
    log = capsys.readouterr().out
    assert sys.executable in log
    assert "Excluded local project: flowgraph==0.1.8" in log
    assert "all 1 other installed distributions" in log
    assert "pytest==8.0" in log


def test_snapshot_cli_fails_closed(tmp_path: Path, monkeypatch, capsys) -> None:
    output = tmp_path / "requirements.txt"
    monkeypatch.setattr(sys, "argv", ["audit_requirements.py", "--output", str(output)])
    monkeypatch.setattr(AUDIT, "distributions", list)
    assert AUDIT.main() == 1
    assert not output.exists()
    assert "Audit snapshot failed" in capsys.readouterr().err


def test_real_snapshot_matches_installed_environment(tmp_path: Path) -> None:
    from importlib.metadata import distributions

    output = tmp_path / "requirements.txt"
    result = subprocess.run(
        [sys.executable, str(ROOT / "packaging/audit_requirements.py"), "--output", str(output)],
        capture_output=True,
        text=True,
        check=True,
    )
    pins, version = AUDIT.snapshot(distributions())
    assert output.read_text().splitlines() == pins
    assert f"Excluded local project: flowgraph=={version}" in result.stdout
    assert any(pin.startswith("muscat==") for pin in pins)
    assert any(pin.startswith("vtk==") for pin in pins)


def test_workflow_audits_explicit_project_snapshot_without_suppression() -> None:
    workflow = (ROOT / ".github/workflows/build-packages.yml").read_text()
    test_job = workflow.split("\n  test:\n", 1)[1].split("\n  build:\n", 1)[0]
    snapshot = "uv run --no-sync python packaging/audit_requirements.py --output .validation-dist/audit-requirements.txt"
    audit = "uvx --from pip-audit pip-audit --requirement .validation-dist/audit-requirements.txt --no-deps --disable-pip --strict"
    assert snapshot in test_job
    assert audit in test_job
    assert test_job.index("uv sync --locked") < test_job.index(snapshot) < test_job.index(audit)
    for bypass in ("continue-on-error", "--ignore-vuln", "|| true", "--fix"):
        assert bypass not in test_job
    guide = (ROOT / "packaging/README.md").read_text()
    assert snapshot in guide and audit in guide
