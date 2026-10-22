"""Install one built distribution in a fresh environment and test it in isolation."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path


def test_artifact(artifacts: Path, kind: str, root: Path) -> None:
    """Resolve dependencies normally, then exercise only the installed package."""
    pattern = {"wheel": "*.whl", "sdist": "*.tar.gz"}[kind]
    candidates = sorted(artifacts.resolve().glob(pattern))
    if len(candidates) != 1:
        raise ValueError(f"Expected exactly one {kind} in {artifacts}, found {len(candidates)}")
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    uv = shutil.which("uv")
    if uv is None:
        raise ValueError("uv must be available on PATH")
    environment = os.environ.copy()
    # Do not allow checkout paths or an activated project environment to leak in.
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
        environment.pop(key, None)
    # The CLI renders Unicode on Windows too, including when stdout is captured.
    environment["PYTHONUTF8"] = "1"
    with tempfile.TemporaryDirectory(prefix=f"flowgraph-{kind}-") as temporary:
        work = Path(temporary)
        if work.resolve().is_relative_to(root.resolve()):
            raise ValueError("Temporary test directory must be outside the source checkout")
        venv = work / "venv"
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        smoke = work / "smoke_installed.py"
        shutil.copyfile(root / "packaging/smoke_installed.py", smoke)
        commands = [
            [uv, "venv", "--python", sys.executable, str(venv)],
            [uv, "pip", "install", "--python", str(python), str(candidates[0])],
            [uv, "pip", "check", "--python", str(python)],
            [
                str(python),
                "-I",
                str(smoke),
                "--version",
                version,
                "--source-root",
                str(root.resolve()),
            ],
        ]
        for command in commands:
            print("Running:", " ".join(command), flush=True)
            subprocess.run(command, cwd=work, env=environment, check=True)


def main() -> int:
    """Run without syncing or importing the development checkout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--kind", choices=("wheel", "sdist"), required=True)
    args = parser.parse_args()
    try:
        test_artifact(args.artifacts, args.kind, Path(__file__).resolve().parents[1])
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Artifact test failed: {error}", file=sys.stderr)
        return 1
    print(f"Installed {args.kind} smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
