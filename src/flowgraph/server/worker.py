"""Private subprocess entry point: execute one request outside the HTTP process."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    from flowgraph.application.workflow_execution import execute_workflow_json

    request, response = map(Path, sys.argv[1:])
    response.write_text(
        execute_workflow_json(request.read_text(encoding="utf-8")), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
