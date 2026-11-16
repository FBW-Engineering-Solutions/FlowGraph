"""Private subprocess entry point: execute one request outside the HTTP process."""

from __future__ import annotations

import argparse
import json
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def progress_writer(response: Path):
    """Append complete events to a private job file, independent of node stdout."""
    with response.with_name("progress.jsonl").open("w", encoding="utf-8") as stream:

        def report(event):
            stream.write(json.dumps(event) + "\n")
            stream.flush()

        yield report


def main() -> None:
    import sys

    from flowgraph.server.packages import checked_directory

    extra_packages = checked_directory(Path.cwd())
    if extra_packages.is_dir():
        # No site.addsitedir: do not execute arbitrary .pth startup hooks.
        sys.path.append(str(extra_packages))
    from flowgraph.application.node_registry import create_node_registry
    from flowgraph.application.workflow_execution import execute_workflow_json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin", action="append", default=[], type=Path)
    parser.add_argument("--session", type=Path)
    parser.add_argument("files", nargs="*", type=Path)
    args = parser.parse_args()
    registry = create_node_registry(plugins=args.plugin)
    workspace = Path.cwd()
    if args.session is not None:
        command = args.session / "command.json"
        while True:
            if not command.exists():
                time.sleep(0.02)
                continue
            payload = json.loads(command.read_text(encoding="utf-8"))
            command.unlink()
            request, response = Path(payload["request"]), Path(payload["response"])
            envelope = json.loads(request.read_text(encoding="utf-8"))
            with progress_writer(response) as report:
                result = execute_workflow_json(
                    json.dumps(envelope["workflow"]),
                    envelope["options"],
                    registry=registry,
                    workspace=workspace,
                    on_progress=report,
                    on_node_result=lambda result: report({"node_result": result}),
                )
            temporary = response.with_suffix(".tmp")
            temporary.write_text(result, encoding="utf-8")
            temporary.replace(response)
    else:
        request, response = args.files
        with progress_writer(response) as report:
            response.write_text(
                execute_workflow_json(
                    request.read_text(encoding="utf-8"),
                    registry=registry,
                    workspace=workspace,
                    on_progress=report,
                    on_node_result=lambda result: report({"node_result": result}),
                ),
                encoding="utf-8",
            )


if __name__ == "__main__":
    main()
