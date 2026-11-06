"""Private subprocess entry point: execute one request outside the HTTP process."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def main() -> None:
    from flowgraph.application.workflow_execution import execute_workflow_json

    if sys.argv[1] == "--session":
        command = Path(sys.argv[2]) / "command.json"
        while True:
            if not command.exists():
                time.sleep(0.02)
                continue
            payload = json.loads(command.read_text(encoding="utf-8"))
            command.unlink()
            request, response = Path(payload["request"]), Path(payload["response"])
            envelope = json.loads(request.read_text(encoding="utf-8"))
            result = execute_workflow_json(json.dumps(envelope["workflow"]), envelope["options"])
            temporary = response.with_suffix(".tmp")
            temporary.write_text(result, encoding="utf-8")
            temporary.replace(response)
    else:
        request, response = map(Path, sys.argv[1:])
        response.write_text(
            execute_workflow_json(request.read_text(encoding="utf-8")), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
