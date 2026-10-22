"""Headless command-line inspection and execution for FlowGraph workflows."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping, Sequence
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
from flowgraph.application.workflow_defaults import saved_input_default
from flowgraph.application.workflow_io import load_workflow


class WorkflowCliError(ValueError):
    """Raised when command-line workflow arguments or output cannot be handled."""


_ARBITRARY_CODE_NODE_IDS = frozenset({"imagej-script", "imagej-script-file", "user-function"})


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


def inspect_workflow(
    path: str | Path,
    *,
    full: bool = False,
    inputs: Mapping[str, Any] | None = None,
    overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    """Preview interface values and optional graph without executing or saving.

    Parameter overrides apply before saved defaults are resolved. Explicit input
    values take precedence, while unspecified inputs may remain required.
    """
    from flowgraph.application.node_registry import create_node_registry

    registry = create_node_registry()
    workflow = load_workflow(path, registry)
    _apply_overrides(workflow, overrides or {})
    return format_workflow_inspection(workflow, registry, full=full, inputs=inputs)


def format_workflow_inspection(
    workflow: WorkflowGraph,
    registry: NodeRegistry,
    *,
    full: bool = True,
    inputs: Mapping[str, Any] | None = None,
) -> str:
    """Format one workflow as a deterministic vertical graph inspection report.

    Nodes are visited in dependency-safe display order. Inputs, parameters, and
    outputs remain separate sections, reordered internally to reduce crossings.
    Set ``full=False`` for an interface-only report. Code warnings are always
    retained. The formatter defaults to full output for existing Python callers;
    the file inspection service and CLI default to compact output.
    """
    values = inputs if inputs is not None else {}
    _validate_explicit_inputs(workflow, values)
    lines = ["Inputs:"]
    if workflow.inputs:
        for port in workflow.inputs:
            if port.name in values:
                suffix = f"default: {_display_value(values[port.name])} (--input)"
            else:
                try:
                    default = saved_input_default(workflow, port)
                except ValueError:
                    suffix = "default: (conflicting saved values; provide --input)"
                else:
                    suffix = (
                        f"default: {_display_value(default[0])}"
                        if default is not None
                        else "default: (none; required)"
                    )
            lines.append(
                f"  {port.name}: {port.data_type.label} ({port.node_id}.{port.node_port})  {suffix}"
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

    code_nodes = _arbitrary_code_nodes(workflow, registry)
    if code_nodes:
        lines.append("Warning: This workflow contains nodes that execute arbitrary code:")
        lines.extend(f"  {node}" for node in code_nodes)
        lines.append("  Review and trust this code before running the workflow.")

    if full:
        lines.append("Workflow:")
        if not workflow.nodes:
            lines.append("  (empty)")
        else:
            lines.extend(_format_graph(workflow, registry, indent="  "))
    return "\n".join(lines)


def _arbitrary_code_nodes(
    workflow: WorkflowGraph, registry: NodeRegistry, *, prefix: str = ""
) -> list[str]:
    """List arbitrary-code nodes, including those inside nested workflows."""
    found: list[str] = []
    for node in workflow.nodes:
        address = f"{prefix}{node.id}"
        if node.definition_id in _ARBITRARY_CODE_NODE_IDS:
            label = registry.require(node.definition_id).label
            found.append(f"({node.definition_id})[{address}] {label}")
        if node.subworkflow is not None:
            found.extend(_arbitrary_code_nodes(node.subworkflow, registry, prefix=f"{address}/"))
    return found


def _format_graph(workflow: WorkflowGraph, registry: NodeRegistry, *, indent: str) -> list[str]:
    """Choose a dependency-safe display order with fewer visible crossings.

    Compare stable topological order with a greedy ready-node schedule that
    favors closing lanes over opening them. Score the actual rendered junctions,
    then vertical lane length; keep the stable order on ties. This is a heuristic,
    not a guarantee of the global minimum. Execution order is never modified.
    """
    stable = workflow.topological_order()
    incoming: dict[str, list[str]] = {node_id: [] for node_id in stable}
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in stable}
    consumers: dict[tuple[str, str], list[str]] = {}
    incoming_outputs: dict[str, set[tuple[str, str]]] = {node_id: set() for node_id in stable}
    outgoing_outputs: dict[str, set[str]] = {node_id: set() for node_id in stable}
    for edge in workflow.edges:
        outgoing[edge.source_node].append(edge.target_node)
        incoming[edge.target_node].append(edge.source_node)
        output = (edge.source_node, edge.source_port)
        consumers.setdefault(output, []).append(edge.target_node)
        incoming_outputs[edge.target_node].add(output)
        outgoing_outputs[edge.source_node].add(edge.source_port)
    rank = {node_id: index for index, node_id in enumerate(stable)}
    remaining = {node_id: len(incoming[node_id]) for node_id in stable}
    ready = {node_id for node_id in stable if not remaining[node_id]}
    greedy: list[str] = []
    pending_consumers = {output: len(targets) for output, targets in consumers.items()}
    while ready:

        def closing_lanes(candidate: str) -> int:
            return sum(
                pending_consumers[output] == consumers[output].count(candidate)
                for output in incoming_outputs[candidate]
            )

        node_id = min(
            ready,
            key=lambda candidate: (
                len(outgoing_outputs[candidate]) - closing_lanes(candidate),
                -closing_lanes(candidate),
                rank[candidate],
            ),
        )
        ready.remove(node_id)
        greedy.append(node_id)
        for output in incoming_outputs[node_id]:
            pending_consumers[output] -= consumers[output].count(node_id)
        for target in outgoing[node_id]:
            remaining[target] -= 1
            if remaining[target] == 0:
                ready.add(target)

    def score(lines: list[str]) -> tuple[int, int]:
        # Exclude inherited indentation when optimizing a nested report.
        content = "\n".join(line.removeprefix(indent) for line in lines)
        return content.count("┼"), content.count("│")

    baseline = _render_graph(workflow, registry, indent=indent, order=stable)
    if tuple(greedy) == stable:
        return baseline
    candidate = _render_graph(workflow, registry, indent=indent, order=tuple(greedy))
    return candidate if score(candidate) < score(baseline) else baseline


def _render_graph(
    workflow: WorkflowGraph,
    registry: NodeRegistry,
    *,
    indent: str,
    order: tuple[str, ...],
    optimize_ports: bool = True,
) -> list[str]:
    """Render one shared lane per source output in topological node order.

    A lane opens on its output line, branches at intermediate consumers, and
    closes at its last consumer. Closed lanes can be reused by later outputs.
    Endpoint addresses disambiguate fan-out and crossing horizontal lines.
    Disconnected nodes are listed first, as they need no connection lanes.
    """
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

    pending: dict[tuple[str, str], int] = {}
    for edge in workflow.edges:
        output = (edge.source_node, edge.source_port)
        pending[output] = pending.get(output, 0) + 1
    lines: list[str] = []
    lanes: list[tuple[str, str] | None] = []

    def prefix() -> str:
        # Connection endpoints occupy two columns beyond the lane area (▶/─ and space).
        endpoint_padding = "  " if lanes else ""
        return (
            indent
            + "".join("│  " if edge is not None else "   " for edge in lanes)
            + endpoint_padding
        )

    def connection(output: tuple[str, str], text: str, *, opening: bool) -> None:
        if opening:
            lane = next((index for index, value in enumerate(lanes) if value is None), len(lanes))
            if lane == len(lanes):
                lanes.append(output)
            else:
                lanes[lane] = output
        else:
            lane = lanes.index(output)
            pending[output] -= 1
        closing = not opening and pending[output] == 0
        path = "".join("│  " if value is not None else "   " for value in lanes[:lane])
        path += "┌──" if opening else "└──" if closing else "├──"
        path += "".join("┼──" if value is not None else "───" for value in lanes[lane + 1 :])
        endpoint = "─ " if opening else "▶ "
        lines.append(f"{indent}{path}{endpoint}{text}")
        if closing:
            lanes[lane] = None

    disconnected = [node_id for node_id in order if not incoming[node_id] and not outgoing[node_id]]
    connected = [node_id for node_id in order if incoming[node_id] or outgoing[node_id]]
    for node_id in [*disconnected, *connected]:
        if lines:
            lines.append(prefix().rstrip())
        # Trim unused trailing lanes only between nodes so each node's ports align.
        while lanes and lanes[-1] is None:
            lanes.pop()
        # Reserve the whole node's width before its header. Incoming lanes become
        # available before outputs open, but new outgoing lanes must not shift
        # later ports to the right within the same node.
        consumed: dict[tuple[str, str], int] = {}
        for edge in incoming[node_id]:
            output = (edge.source_node, edge.source_port)
            consumed[output] = consumed.get(output, 0) + 1
        available = lanes.count(None) + sum(
            count == pending[output] for output, count in consumed.items()
        )
        output_count = len({edge.source_port for edge in outgoing[node_id]})
        lanes.extend([None] * max(0, output_count - available))
        node = workflow.require_node(node_id)
        definition = registry.require(node.definition_id)
        ports = definition.ports_for_instance(node)
        lines.append(f"{prefix()}{_node_header(node.definition_id, node.id, definition.label)}")

        input_edges = {edge.target_port: edge for edge in incoming[node_id]}

        def render_inputs(
            category: list[PortDefinition], input_edges: Mapping[str, WorkflowEdge]
        ) -> None:
            # Close rightmost lanes first, but never move a port across categories.
            connected = [port for port in category if port.name in input_edges]
            if optimize_ports:
                connected.sort(
                    key=lambda port: (
                        -lanes.index(
                            (input_edges[port.name].source_node, input_edges[port.name].source_port)
                        )
                    )
                )
            for port in connected:
                edge = input_edges[port.name]
                connection(
                    (edge.source_node, edge.source_port),
                    f"{_port_text('P' if port.is_param else 'I', port)}"
                    f" (from {edge.source_node}.{edge.source_port})",
                    opening=False,
                )
            for port in category:
                if port.name not in input_edges and not port.is_param:
                    lines.append(f"{prefix()}{_port_text('I', port)}")

        render_inputs(
            [port for port in ports if port.direction is PortDirection.INPUT and not port.is_param],
            input_edges,
        )
        render_inputs(
            [port for port in ports if port.direction is PortDirection.INPUT and port.is_param],
            input_edges,
        )
        for parameter in definition.parameters:
            if parameter.name in input_edges:
                continue
            value = node.parameters.get(parameter.name, parameter.default)
            lines.append(
                f"{prefix()}(P) {parameter.name} - {parameter.kind.label}: {_display_value(value)}"
            )
        output_ports = [port for port in ports if port.direction is PortDirection.OUTPUT]
        if optimize_ports:
            # First-fit lanes open left to right. Put longer-lived outputs on the
            # left, so earlier consumers can close right-hand lanes without crossing.
            output_ports.sort(
                key=lambda port: (
                    -max(
                        (
                            order_index[edge.target_node]
                            for edge in outgoing[node_id]
                            if edge.source_port == port.name
                        ),
                        default=-1,
                    )
                )
            )
        for port in output_ports:
            edges = [edge for edge in outgoing[node_id] if edge.source_port == port.name]
            if edges:
                destinations = ", ".join(f"{edge.target_node}.{edge.target_port}" for edge in edges)
                connection(
                    (node_id, port.name),
                    f"{_port_text('O', port)} (to {destinations})",
                    opening=True,
                )
            else:
                lines.append(f"{prefix()}{_port_text('O', port)}")

        if node.subworkflow is not None:
            # Child connections have their own lane space, separate from the parent.
            child_indent = f"{prefix()}  "
            lines.append(f"{prefix()}subworkflow:")
            if node.subworkflow.nodes:
                lines.extend(_format_graph(node.subworkflow, registry, indent=child_indent))
            else:
                lines.append(f"{child_indent}(empty)")
    return lines


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
    injected = resolve_workflow_inputs(workflow, inputs or {})
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


def _validate_explicit_inputs(workflow: WorkflowGraph, values: Mapping[str, Any]) -> None:
    """Validate only supplied inputs, allowing incomplete inspection previews."""
    unknown = set(values).difference(port.name for port in workflow.inputs)
    if unknown:
        raise WorkflowCliError(f"Unknown workflow inputs: {sorted(unknown)!r}")
    for port in workflow.inputs:
        if port.name in values and not port.data_type.accepts(values[port.name]):
            raise WorkflowCliError(
                f"Workflow input {port.name!r} expected {port.data_type.label}, "
                f"got {type(values[port.name]).__name__}"
            )


def resolve_workflow_inputs(
    workflow: WorkflowGraph,
    values: Mapping[str, Any],
    *,
    on_warning: Callable[[str], None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Resolve public inputs, falling back to saved downstream parameters.

    Warnings go to stderr unless a host (such as the browser) supplies a sink.
    """
    _validate_explicit_inputs(workflow, values)
    resolved = dict(values)
    warnings = []
    for port in workflow.inputs:
        if port.name in resolved:
            continue
        default = saved_input_default(workflow, port)
        if default is not None:
            value, addresses = default
            resolved[port.name] = value
            warnings.append(
                f"flowgraph: Warning: Workflow input {port.name!r} was not provided; "
                f"using saved parameter value {_display_value(value)} from {', '.join(addresses)}."
            )
    missing = [port.name for port in workflow.inputs if port.name not in resolved]
    if missing:
        raise WorkflowCliError(f"Missing required workflow inputs: {', '.join(missing)}")
    injected: dict[str, dict[str, Any]] = {}
    for port in workflow.inputs:
        value = resolved[port.name]
        if not port.data_type.accepts(value):
            raise WorkflowCliError(
                f"Workflow input {port.name!r} expected {port.data_type.label}, "
                f"got {type(value).__name__}"
            )
        injected.setdefault(port.node_id, {})[port.node_port] = value
    for warning in warnings:
        if on_warning is None:
            print(warning, file=sys.stderr)
        else:
            on_warning(warning)
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
