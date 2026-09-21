"""Headless command-line inspection and execution for FlowGraph workflows."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from flowgraph.application.workflow_core import (
    NodeRegistry,
    PortDefinition,
    PortDirection,
    WorkflowEdge,
    WorkflowExecutor,
    WorkflowGraph,
    WorkflowRunResult,
)
from flowgraph.application.workflow_io import load_workflow


class WorkflowCliError(ValueError):
    """Raised when command-line workflow arguments or output cannot be handled."""


def parse_assignment(value: str, *, option: str) -> tuple[str, Any]:
    """Parse a ``name=value`` command-line assignment.

    Values are decoded as JSON when possible. Values that are not valid JSON are
    retained as strings, which makes unquoted paths and ordinary text convenient.
    """
    name, separator, raw_value = value.partition("=")
    if not separator or not name:
        raise WorkflowCliError(f"{option} expects NAME=VALUE, got {value!r}")
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        parsed = raw_value
    return name, parsed


def parse_inputs(assignments: Sequence[str]) -> dict[str, Any]:
    """Parse workflow input assignments and reject duplicate names."""
    result: dict[str, Any] = {}
    for assignment in assignments:
        name, value = parse_assignment(assignment, option="--input")
        if name in result:
            raise WorkflowCliError(f"Workflow input {name!r} was provided more than once")
        result[name] = value
    return result


def parse_overrides(assignments: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Parse ``node-id.parameter=value`` assignments into executor overrides."""
    result: dict[str, dict[str, Any]] = {}
    for assignment in assignments:
        address, value = parse_assignment(assignment, option="--override")
        node_id, separator, parameter = address.partition(".")
        if not separator or not node_id or not parameter:
            raise WorkflowCliError(
                f"--override expects NODE-ID.PARAMETER=VALUE, got {assignment!r}"
            )
        if parameter in result.setdefault(node_id, {}):
            raise WorkflowCliError(
                f"Parameter override {node_id}.{parameter} was provided more than once"
            )
        result[node_id][parameter] = value
    return result


def inspect_workflow(path: str | Path) -> str:
    """Load a workflow and return its inputs, outputs, and directed ASCII graph."""
    from flowgraph.application.node_registry import create_node_registry

    registry = create_node_registry()
    workflow = load_workflow(path, registry)
    return format_workflow_inspection(workflow, registry)


def format_workflow_inspection(workflow: WorkflowGraph, registry: NodeRegistry) -> str:
    """Format one workflow as a deterministic vertical tree inspection report.

    Nodes are visited in stable topological order. Edges are rendered below the
    output port that transports them, and every connected input is shown in the
    target node's input section before its parameters and outputs.
    """
    lines = ["Inputs:"]
    if workflow.inputs:
        lines.extend(
            f"  {port.name}: {port.data_type.label} ({port.node_id}.{port.node_port})"
            for port in workflow.inputs
        )
    else:
        lines.append("  (none)")

    lines.append("Outputs:")
    if workflow.outputs:
        lines.extend(
            f"  {port.name}: {port.data_type.label} ({port.node_id}.{port.node_port})"
            for port in workflow.outputs
        )
    else:
        lines.append("  (none)")

    lines.append("Workflow:")
    if not workflow.nodes:
        lines.append("  (empty)")
    else:
        lines.extend(_format_graph(workflow, registry, indent="  "))
    return "\n".join(lines)


def _format_graph(workflow: WorkflowGraph, registry: NodeRegistry, *, indent: str) -> list[str]:
    """Return a vertical tree rendering of *workflow* at *indent*.

    Disconnected nodes are listed first. Connected nodes are then rendered from
    stable graph roots. Before a shared target is rendered, its unresolved input
    sources are rendered first so all of the target's connected inputs appear
    together before its outputs. Unicode box-drawing characters make the
    continuation of each connection explicit in terminal output.
    """
    order = workflow.topological_order()
    order_index = {node_id: index for index, node_id in enumerate(order)}
    incoming = {node_id: [] for node_id in order}
    outgoing = {node_id: [] for node_id in order}
    for edge in workflow.edges:
        if edge.source_node in outgoing and edge.target_node in incoming:
            outgoing[edge.source_node].append(edge)
            incoming[edge.target_node].append(edge)
    for edges in incoming.values():
        edges.sort(
            key=lambda edge: (
                order_index.get(edge.source_node, len(order)),
                edge.source_port,
                edge.target_port,
                edge.source_node,
            )
        )
    for edges in outgoing.values():
        edges.sort(
            key=lambda edge: (
                order_index.get(edge.target_node, len(order)),
                edge.source_port,
                edge.target_port,
                edge.target_node,
            )
        )

    rendered: set[str] = set()
    lines: list[str] = []

    def render_node(
        node_id: str,
        indent: list[str],
        connected_edge: WorkflowEdge | None = None,
    ) -> None:
        node = workflow.require_node(node_id)
        definition = registry.require(node.definition_id)
        ports = definition.ports_for_instance(node)
        rendered.add(node_id)
        lines.append(f"{indent[0]}{_node_header(node.definition_id, node.id, definition.label)}")

        connected_port = None
        if connected_edge is not None:
            connected_port = next(
                (
                    port
                    for port in ports
                    if port.direction is PortDirection.INPUT
                    and port.name == connected_edge.target_port
                ),
                None,
            )
        if connected_port is not None:
            lines.append(
                f"{indent[1]}{_port_text('P' if connected_port.is_param else 'I', connected_port)}"
            )

        connected_input_names = {
            edge.target_port for edge in incoming[node_id] if edge.source_node in rendered
        }
        if connected_port is not None:
            connected_input_names.add(connected_port.name)
        has_additional_connected_input = False
        for edge in incoming[node_id]:
            if connected_port is not None and edge.target_port == connected_port.name:
                continue
            target_port = definition.input_for_instance(edge.target_port, node)
            if target_port is not None:
                lines.append(
                    f"{_additional_input_prefix(indent)}"
                    f"{_port_text('P' if target_port.is_param else 'I', target_port)}"
                )
                has_additional_connected_input = True
        if has_additional_connected_input:
            indent = _continued_indent(indent)
        for port in ports:
            if (
                port.direction is PortDirection.INPUT
                and not port.is_param
                and port.name not in connected_input_names
            ):
                lines.append(f"{indent[2]}{_port_text('I', port)}")
        for parameter in definition.parameters:
            if parameter.name in connected_input_names:
                continue
            value = node.parameters.get(parameter.name, parameter.default)
            lines.append(
                f"{indent[2]}(P) {parameter.name} - {parameter.kind.label}: {_display_value(value)}"
            )
        for port in ports:
            if port.direction is not PortDirection.OUTPUT:
                continue
            lines.append(f"{indent[2]}{_port_text('O', port)}")
            for edge in outgoing[node_id]:
                if edge.source_port != port.name:
                    continue
                target = workflow.get_node(edge.target_node)
                if target is None:
                    continue
                if edge.target_node in rendered:
                    continue

                unresolved_sources = [
                    candidate
                    for candidate in incoming[edge.target_node]
                    if candidate.source_node not in rendered and candidate.source_node != node_id
                ]
                for candidate in unresolved_sources:
                    source_node = workflow.get_node(candidate.source_node)
                    if source_node is None or source_node.id in rendered:
                        continue
                    lines.append(f"{indent[3]}│")
                    render_node(
                        source_node.id,
                        _carried_indent(indent[3]),
                    )

                if edge.target_node in rendered:
                    continue

                lines.append(f"{indent[3]}│")
                render_node(
                    edge.target_node,
                    _child_indent(indent[3]),
                    connected_edge=edge,
                )

        if node.subworkflow is not None:
            lines.append(f"{indent[0]}subworkflow:")
            if node.subworkflow.nodes:
                lines.extend(_format_graph(node.subworkflow, registry, indent=f"{indent[0]}  "))
            else:
                lines.append(f"{indent[0]}  (empty)")

    disconnected = [node_id for node_id in order if not incoming[node_id] and not outgoing[node_id]]
    roots = [node_id for node_id in order if not incoming[node_id] and node_id not in disconnected]
    remaining = [
        node_id for node_id in order if node_id not in disconnected and node_id not in roots
    ]

    top_level_groups = [*disconnected, *roots, *remaining]
    for node_id in top_level_groups:
        if node_id in rendered:
            continue
        if lines:
            lines.append("")
        render_node(node_id, [indent, indent, indent, "   "])
    return lines


def _child_indent(edge_base: str) -> list[str]:
    """Build indentation slots for a node reached by a primary edge."""
    return [
        f"{edge_base}│ ",
        f"{edge_base}└─",
        f"{edge_base}  ",
        f"{edge_base}   ",
    ]


def _carried_indent(edge_base: str) -> list[str]:
    """Build indentation slots for a node reached as an additional source."""
    return [
        f"{edge_base}│ ",
        f"{edge_base}│ ",
        f"{edge_base}│ ",
        f"{edge_base}│  ",
    ]


def _additional_input_prefix(indent: list[str]) -> str:
    """Return the prefix for an additional connected input on the current node."""
    return f"{indent[3].split('│', 1)[0]}└────"


def _continued_indent(indent: list[str]) -> list[str]:
    """Return indentation after an additional input closes its branch."""
    return [slot.replace("│", " ") for slot in indent]


def _node_header(definition_id: str, node_id: str, label: str) -> str:
    """Format a node definition/instance header."""
    return f"({definition_id})[{node_id}] {label}"


def _port_text(kind: str, port: PortDefinition) -> str:
    """Format one resolved node port."""
    return f"({kind}) {port.name} - {port.data_type.label}"


def execute_cli_workflow(
    path: str | Path,
    *,
    inputs: Mapping[str, Any] | None = None,
    overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[WorkflowGraph, WorkflowRunResult]:
    """Load and execute a workflow using published inputs and parameter overrides."""
    from flowgraph.application.node_registry import create_node_registry

    registry = create_node_registry()
    workflow = load_workflow(path, registry)
    _apply_overrides(workflow, overrides or {})
    injected = _resolve_inputs(workflow, inputs or {})
    return workflow, WorkflowExecutor(registry).run(workflow, initial_inputs=injected)


def workflow_outputs(workflow: WorkflowGraph, result: WorkflowRunResult) -> dict[str, Any]:
    """Extract public workflow outputs from an execution result."""
    return {
        port.name: result.node_outputs[port.node_id][port.node_port] for port in workflow.outputs
    }


def format_workflow_outputs(outputs: Mapping[str, Any]) -> str:
    """Format workflow outputs for terminal display."""
    lines = ["Outputs:"]
    if not outputs:
        return "\n".join([*lines, "  (none)"])
    lines.extend(f"  {name}: {_display_value(value)}" for name, value in outputs.items())
    return "\n".join(lines)


def write_json_output(outputs: Mapping[str, Any], path: str | Path) -> Path:
    """Write JSON-safe workflow outputs to *path* and return its resolved path."""
    destination = Path(path).expanduser()
    if not destination.parent.is_dir():
        raise WorkflowCliError(f"Output directory does not exist: {destination.parent}")
    try:
        payload = _json_safe(outputs)
        destination.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (OSError, TypeError, ValueError) as error:
        raise WorkflowCliError(
            f"Could not write JSON output to '{destination}': {error}"
        ) from error
    return destination.resolve()


def _resolve_inputs(
    workflow: WorkflowGraph, values: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    unknown = set(values).difference(port.name for port in workflow.inputs)
    if unknown:
        raise WorkflowCliError(f"Unknown workflow inputs: {sorted(unknown)!r}")
    missing = [port.name for port in workflow.inputs if port.name not in values]
    if missing:
        raise WorkflowCliError(f"Missing required workflow inputs: {', '.join(missing)}")
    injected: dict[str, dict[str, Any]] = {}
    for port in workflow.inputs:
        value = values[port.name]
        if not port.data_type.accepts(value):
            raise WorkflowCliError(
                f"Workflow input {port.name!r} expected {port.data_type.label}, "
                f"got {type(value).__name__}"
            )
        injected.setdefault(port.node_id, {})[port.node_port] = value
    return injected


def _apply_overrides(workflow: WorkflowGraph, overrides: Mapping[str, Mapping[str, Any]]) -> None:
    from flowgraph.application.node_registry import create_node_registry

    registry = create_node_registry()
    for node_id, parameters in overrides.items():
        node = workflow.get_node(node_id)
        if node is None:
            raise WorkflowCliError(f"Parameter override references unknown node {node_id!r}")
        definition = registry.require(node.definition_id)
        known = {parameter.name for parameter in definition.parameters}
        unknown = set(parameters).difference(known)
        if unknown:
            raise WorkflowCliError(f"Unknown parameters for node {node_id!r}: {sorted(unknown)!r}")
        node.parameters.update(parameters)


def _display_value(value: Any) -> str:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return repr(value)
    return f"<{type(value).__name__}: {value}>"


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "mode") and hasattr(value, "size"):
        return {"type": type(value).__name__, "mode": value.mode, "size": list(value.size)}
    if type(value).__name__ == "MeshDocument":
        return {"type": type(value).__name__, "description": str(value)}
    return repr(value)
