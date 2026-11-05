"""Snapshot the invoking project's installed distributions for dependency auditing."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable
from importlib.metadata import Distribution, distributions
from pathlib import Path


def snapshot(installed: Iterable[Distribution]) -> tuple[list[str], str]:
    """Return sorted exact pins, excluding only the installed FlowGraph project."""
    versions: dict[str, str] = {}
    for distribution in installed:
        name = distribution.metadata.get("Name", "")
        version = distribution.version
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", name):
            raise ValueError(f"Invalid installed distribution name: {name!r}")
        if not isinstance(version, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9.!+_-]*", version
        ):
            raise ValueError(f"Invalid installed version for {name}: {version!r}")
        name = re.sub(r"[-_.]+", "-", name).lower()
        if name in versions and versions[name] != version:
            raise ValueError(f"Conflicting installed versions for {name}")
        versions[name] = version
    if "flowgraph" not in versions:
        raise ValueError("FlowGraph is not installed; invoke through the project interpreter")
    project_version = versions.pop("flowgraph")
    if not versions:
        raise ValueError("No installed dependencies found to audit")
    return [f"{name}=={version}" for name, version in sorted(versions.items())], project_version


def main() -> int:
    """Write and log the inventory without resolving or installing dependencies."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        pins, project_version = snapshot(distributions())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("\n".join(pins) + "\n", encoding="utf-8")
    except (ValueError, OSError) as error:
        print(f"Audit snapshot failed: {error}", file=sys.stderr)
        return 1
    print(f"Audit interpreter: {sys.executable}")
    print(f"Audit environment prefix: {sys.prefix}")
    print(f"Excluded local project: flowgraph=={project_version}")
    print(f"Audit scope: all {len(pins)} other installed distributions, including test/dev tools")
    print(f"Requirements: {args.output.resolve()}")
    print("\n".join(pins))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
