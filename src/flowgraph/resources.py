"""Current-working-directory-independent access to packaged FlowGraph resources."""

from __future__ import annotations

from pathlib import Path

import flowgraph

PACKAGE_ROOT = Path(__file__).resolve().parent


def package_resource_path(*parts: str, required: bool = True) -> Path:
    """Return a path inside the installed package and optionally require it to exist.

    PyInstaller gives bundled modules meaningful ``__file__`` paths inside its
    collected application directory, so this works in source, wheel, and onedir
    executions without depending on the process working directory.
    """
    candidates = [Path(root).joinpath(*parts) for root in flowgraph.__path__]
    path = next(
        (candidate for candidate in candidates if candidate.exists()), PACKAGE_ROOT.joinpath(*parts)
    )
    if required and not path.exists():
        resource = "/".join(parts) or "."
        raise FileNotFoundError(
            f"Required FlowGraph resource {resource!r} was not included at {path}. "
            "Install the matching FlowGraph core and desktop distributions, then rebuild the artifact."
        )
    return path
