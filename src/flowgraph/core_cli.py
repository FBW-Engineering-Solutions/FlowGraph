"""Headless command-line entry point for the binary FlowGraph core wheel."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from flowgraph.application.workflow_cli import (
    WorkflowCliError,
    execute_cli_workflow,
    format_workflow_outputs,
    inspect_workflow,
    parse_inputs,
    parse_overrides,
    workflow_outputs,
    write_json_output,
)
from flowgraph.application.workflow_core import WorkflowError


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for headless workflow execution."""
    parser = argparse.ArgumentParser(description="Inspect or execute FlowGraph workflows.")
    commands = parser.add_subparsers(dest="command", required=True)

    inspect_parser = commands.add_parser(
        "inspect", help="print workflow inputs and outputs; add --full for the graph"
    )
    inspect_parser.add_argument("workflow", type=str, help="workflow JSON file")
    inspect_parser.add_argument(
        "--full", "-f", action="store_true", help="include the full workflow graph"
    )

    run_parser = commands.add_parser("run", help="execute a workflow without opening the UI")
    run_parser.add_argument("workflow", type=str, help="workflow JSON file")
    for command_parser in (inspect_parser, run_parser):
        command_parser.add_argument(
            "--input",
            "-i",
            action="append",
            default=[],
            metavar="NAME=VALUE",
            help="set a published workflow input; JSON values are decoded when possible",
        )
        command_parser.add_argument(
            "--override",
            action="append",
            default=[],
            metavar="NODE-ID.PARAMETER=VALUE",
            help="override a node parameter for this invocation",
        )
    run_parser.add_argument(
        "--json-output",
        type=str,
        metavar="FILE",
        help="write public workflow outputs as JSON to FILE",
    )
    serve_parser = commands.add_parser(
        "serve", help="start the experimental loopback execution API"
    )
    serve_parser.add_argument(
        "--workspace", type=Path, required=True, help="existing workspace directory"
    )
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--execution-timeout", type=float, default=120)
    serve_parser.add_argument("--max-request-bytes", type=int, default=16 << 20)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Validate arguments and run a headless FlowGraph workflow command."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "serve":
            from flowgraph.server.http import LocalServer

            with LocalServer(
                args.workspace,
                port=args.port,
                execution_timeout=args.execution_timeout,
                max_request=args.max_request_bytes,
            ) as server:
                print(f"Experimental FlowGraph API: {server.origin}", flush=True)
                print(f"Bearer token: {server.token}", flush=True)
                print("Trusted local workflows only; native Python is not sandboxed.", flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
        elif args.command == "inspect":
            print(
                inspect_workflow(
                    args.workflow,
                    full=args.full,
                    inputs=parse_inputs(args.input),
                    overrides=parse_overrides(args.override),
                )
            )
        else:
            workflow, result = execute_cli_workflow(
                args.workflow,
                inputs=parse_inputs(args.input),
                overrides=parse_overrides(args.override),
            )
            outputs = workflow_outputs(workflow, result)
            if args.json_output:
                write_json_output(outputs, args.json_output)
            else:
                print(format_workflow_outputs(outputs))
    except (OSError, ValueError, KeyError, WorkflowError, WorkflowCliError) as error:
        print(f"flowgraph: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
