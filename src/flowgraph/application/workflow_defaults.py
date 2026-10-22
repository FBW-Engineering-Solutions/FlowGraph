"""Resolve saved public-input values without executing workflow nodes."""

from __future__ import annotations

from typing import Any, get_args

from flowgraph.application.workflow_core import WorkflowGraph, WorkflowPort


def saved_input_default(
    workflow: WorkflowGraph, port: WorkflowPort
) -> tuple[Any, tuple[str, ...]] | None:
    """Return a compatible, unambiguous saved value and its parameter addresses.

    Boundary nodes are followed downstream and composite inputs are followed
    into their child workflow. Only persisted instance parameters are used;
    ordinary data inputs without saved values do not manufacture defaults.
    """
    from flowgraph.application.port_conversions import resolve_value_conversion

    candidates = _saved_parameters(workflow, port.node_id, port.node_port, set())
    if not candidates:
        return None
    normalized = []
    for value, address in candidates:
        if (
            port.data_type.id == "VEC3D"
            and get_args(port.data_type.python_type) == (float,)
            and isinstance(value, list)
            and len(value) == 3
            and all(type(component) in (int, float) for component in value)
        ):
            value = [float(component) for component in value]
        if not port.data_type.accepts(value):
            conversion = resolve_value_conversion(value, port.data_type)
            if conversion is None:
                return None
            value = conversion.convert(value)
        if not port.data_type.accepts(value):
            return None
        normalized.append((value, address))
    value = normalized[0][0]
    if any(other != value for other, _ in normalized[1:]):
        raise ValueError(
            f"Conflicting saved parameter values for workflow input {port.name!r}; "
            f"provide --input {port.name}=VALUE"
        )
    return value, tuple(address for _, address in normalized)


def _saved_parameters(
    workflow: WorkflowGraph,
    node_id: str,
    node_port: str,
    visited: set[tuple[int, str, str]],
    prefix: str = "",
) -> list[tuple[Any, str]]:
    key = (id(workflow), node_id, node_port)
    if key in visited:
        return []
    visited = visited | {key}
    node = workflow.require_node(node_id)
    if node_port in node.parameters:
        return [(node.parameters[node_port], f"{prefix}{node_id}.{node_port}")]
    if node.definition_id == "workflow-input" and node_port == "value":
        return [
            candidate
            for edge in workflow.edges
            if edge.source_node == node_id and edge.source_port == "value"
            for candidate in _saved_parameters(
                workflow, edge.target_node, edge.target_port, visited, prefix
            )
        ]
    if node.subworkflow is not None:
        child_port = node.subworkflow.input(node_port)
        if child_port is not None:
            return _saved_parameters(
                node.subworkflow,
                child_port.node_id,
                child_port.node_port,
                visited,
                f"{prefix}{node_id}/",
            )
    return []
