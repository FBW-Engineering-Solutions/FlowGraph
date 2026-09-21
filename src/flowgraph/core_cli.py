"""Headless command-line entry point for the binary FlowGraph core wheel."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

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
        "inspect", help="print workflow inputs, outputs, and its directed ASCII graph"
    )
    inspect_parser.add_argument("workflow", type=str, help="workflow JSON file")

    run_parser = commands.add_parser("run", help="execute a workflow without opening the UI")
    run_parser.add_argument("workflow", type=str, help="workflow JSON file")
    run_parser.add_argument(
        "--input",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="set a published workflow input; JSON values are decoded when possible",
    )
    run_parser.add_argument(
        "--override",
        action="append",
        default=[],
        metavar="NODE-ID.PARAMETER=VALUE",
        help="override a node parameter for this run",
    )
    run_parser.add_argument(
        "--json-output",
        type=str,
        metavar="FILE",
        help="write public workflow outputs as JSON to FILE",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Validate arguments and run a headless FlowGraph workflow command."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            print(inspect_workflow(args.workflow))
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
