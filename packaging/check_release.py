"""Validate release versions without importing FlowGraph or extracting archives."""

from __future__ import annotations

import argparse
import ast
import re
import sys
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path


def check_metadata(data: bytes, version: str, location: str) -> None:
    """Require exactly one matching distribution name and version header."""
    metadata = BytesParser().parsebytes(data)
    for key, expected in (("Name", "flowgraph"), ("Version", version)):
        if metadata.get_all(key) != [expected]:
            raise ValueError(f"{location}: expected {key}: {expected}")


def check_release(root: Path, artifacts: Path, tag: str | None = None) -> str:
    """Check source declarations and require one matching wheel/sdist pair."""
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = project["version"]
    if project["name"] != "flowgraph":
        raise ValueError("Expected the flowgraph distribution")
    if tag is not None and tag != f"v{version}":
        raise ValueError(f"Tag {tag!r} does not match artifact version v{version}")

    tree = ast.parse((root / "src/flowgraph/version.py").read_text(encoding="utf-8"))
    runtime_versions = [
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets
        )
    ]
    if runtime_versions != [version]:
        raise ValueError(f"Runtime version does not match {version}")
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    if [entry["version"] for entry in lock["package"] if entry["name"] == "flowgraph"] != [version]:
        raise ValueError(f"Lockfile version does not match {version}")
    recipe = (root / "packaging/conda/meta.yaml").read_text(encoding="utf-8")
    if re.findall(r'^\{% set version = "([^"]+)" %\}$', recipe, re.MULTILINE) != [version]:
        raise ValueError(f"Conda version does not match {version}")

    wheels = sorted(artifacts.glob("*.whl"))
    sdists = sorted(artifacts.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ValueError("Expected exactly one wheel and one .tar.gz sdist in artifact directory")
    wheel, sdist = wheels[0], sdists[0]
    if wheel.name != f"flowgraph-{version}-py3-none-any.whl":
        raise ValueError(f"Unexpected wheel filename: {wheel.name}")
    if sdist.name != f"flowgraph-{version}.tar.gz":
        raise ValueError(f"Unexpected sdist filename: {sdist.name}")

    with zipfile.ZipFile(wheel) as archive:
        names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if names != [f"flowgraph-{version}.dist-info/METADATA"]:
            raise ValueError(f"{wheel.name}: unexpected wheel metadata paths: {names}")
        check_metadata(archive.read(names[0]), version, wheel.name)
    with tarfile.open(sdist, "r:gz") as archive:
        # Ignore nested egg-info/PKG-INFO; only the top-level metadata is authoritative.
        members = [
            member
            for member in archive.getmembers()
            if member.name.endswith("/PKG-INFO") and member.name.count("/") == 1
        ]
        if len(members) != 1 or members[0].name != f"flowgraph-{version}/PKG-INFO":
            raise ValueError(f"{sdist.name}: expected one top-level PKG-INFO")
        member = members[0]
        if not member.isfile():
            raise ValueError(f"{sdist.name}: PKG-INFO must be a regular file")
        stream = archive.extractfile(member)
        if stream is None:
            raise ValueError(f"{sdist.name}: unreadable PKG-INFO")
        with stream:
            check_metadata(stream.read(), version, sdist.name)
    return version


def main() -> int:
    """Run the release gate locally or against downloaded CI artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--tag", help="Exact release tag, e.g. v0.1.6")
    args = parser.parse_args()
    try:
        version = check_release(args.root, args.artifacts, args.tag)
    except (ValueError, OSError, KeyError, tarfile.TarError, zipfile.BadZipFile) as error:
        print(f"Release validation failed: {error}", file=sys.stderr)
        return 1
    print(
        f"Release validation passed: flowgraph {version}" + (f" ({args.tag})" if args.tag else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
