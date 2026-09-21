"""Versioned JSON persistence and headless execution for FlowGraph workflows."""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from flowgraph.application.workflow_core import (
    NodeInstance,
    NodeRegistry,
    PortDirection,
    WorkflowEdge,
    WorkflowExecutor,
    WorkflowGraph,
    WorkflowPort,
    WorkflowRunResult,
    WorkflowValidationError,
)
from flowgraph.resources import package_resource_path

WORKFLOW_FORMAT = "flowgraph-workflow"
WORKFLOW_FORMAT_VERSION = 2
LEGACY_WORKFLOW_FORMAT_VERSION = 1


class WorkflowPersistenceError(ValueError):
    """Raised when a workflow cannot be serialized or reconstructed safely."""


def workflow_to_dict(workflow: WorkflowGraph) -> dict[str, Any]:
    """Return the authoritative graph as a versioned JSON-compatible mapping."""
    return _workflow_to_dict(workflow, set())


def _workflow_to_dict(workflow: WorkflowGraph, ancestors: set[int]) -> dict[str, Any]:
    """Serialize one workflow and its owned child workflows recursively."""
    if id(workflow) in ancestors:
        raise WorkflowPersistenceError("Workflow contains a recursive nested workflow")
    ancestors = {*ancestors, id(workflow)}
    testdata_root = package_resource_path("testdata").resolve()
    payload = {
        "format": WORKFLOW_FORMAT,
        "version": WORKFLOW_FORMAT_VERSION,
        "nodes": [
            {
                "id": node.id,
                "definition_id": node.definition_id,
                "parameters": {
                    name: _serialize_testdata_value(value, testdata_root)
                    for name, value in node.parameters.items()
                },
                "position": {"x": node.x, "y": node.y},
                **(
                    {"subworkflow": _workflow_to_dict(node.subworkflow, ancestors)}
                    if node.subworkflow is not None
                    else {}
                ),
            }
            for node in workflow.nodes
        ],
        "inputs": [
            {"name": p.name, "node_id": p.node_id, "node_port": p.node_port}
            for p in workflow.inputs
        ],
        "outputs": [
            {"name": p.name, "node_id": p.node_id, "node_port": p.node_port}
            for p in workflow.outputs
        ],
        "edges": [
            {
                "source_node": edge.source_node,
                "source_port": edge.source_port,
                "target_node": edge.target_node,
                "target_port": edge.target_port,
            }
            for edge in workflow.edges
        ],
    }
    try:
        json.dumps(payload)
    except (TypeError, ValueError) as error:
        raise WorkflowPersistenceError(
            f"Workflow contains parameters that cannot be represented as JSON: {error}"
        ) from error
    return payload


def workflow_from_dict(payload: Mapping[str, Any], registry: NodeRegistry) -> WorkflowGraph:
    """Validate and reconstruct an authoritative graph from persisted data."""
    if not isinstance(payload, Mapping):
        raise WorkflowPersistenceError("Workflow JSON root must be an object")
    if payload.get("format") != WORKFLOW_FORMAT:
        raise WorkflowPersistenceError(
            f"Unsupported workflow format {payload.get('format')!r}; expected {WORKFLOW_FORMAT!r}"
        )
    version = payload.get("version")
    if version not in {LEGACY_WORKFLOW_FORMAT_VERSION, WORKFLOW_FORMAT_VERSION}:
        raise WorkflowPersistenceError(
            f"Unsupported workflow version {payload.get('version')!r}; "
            f"expected {LEGACY_WORKFLOW_FORMAT_VERSION} or {WORKFLOW_FORMAT_VERSION}"
        )

    nodes_payload = payload.get("nodes")
    edges_payload = payload.get("edges")
    if not isinstance(nodes_payload, list):
        raise WorkflowPersistenceError("Workflow 'nodes' must be an array")
    if not isinstance(edges_payload, list):
        raise WorkflowPersistenceError("Workflow 'edges' must be an array")

    payload = _resolve_testdata_paths(payload)
    nodes_payload = payload["nodes"]
    graph = WorkflowGraph()
    for index, raw_node in enumerate(nodes_payload):
        node = _parse_node(raw_node, index, registry, version=version)
        try:
            graph.add_node(node)
        except ValueError as error:
            raise WorkflowPersistenceError(str(error)) from error

    for index, raw_edge in enumerate(edges_payload):
        edge = _parse_edge(raw_edge, index)
        try:
            graph.add_edge(edge, registry)
        except WorkflowValidationError as error:
            raise WorkflowPersistenceError(f"Invalid edge at index {index}: {error}") from error
    for index, raw_port in enumerate(payload.get("inputs", [])):
        port = _parse_workflow_port(raw_port, index, graph, registry, "input")
        try:
            graph.export_input(port.name, port.node_id, port.node_port, registry, label=port.label)
        except (ValueError, WorkflowValidationError) as error:
            raise WorkflowPersistenceError(
                f"Invalid workflow input at index {index}: {error}"
            ) from error
    for index, raw_port in enumerate(payload.get("outputs", [])):
        port = _parse_workflow_port(raw_port, index, graph, registry, "output")
        try:
            graph.export_output(port.name, port.node_id, port.node_port, registry, label=port.label)
        except (ValueError, WorkflowValidationError) as error:
            raise WorkflowPersistenceError(
                f"Invalid workflow output at index {index}: {error}"
            ) from error
    try:
        graph.sync_boundary_nodes(registry)
    except (ValueError, WorkflowValidationError) as error:
        raise WorkflowPersistenceError(f"Invalid workflow boundary node: {error}") from error
    return graph


def save_workflow(workflow: WorkflowGraph, path: str | Path) -> Path:
    """Write a workflow to deterministic, human-readable JSON."""
    destination = Path(path).expanduser()
    if not destination.parent.is_dir():
        raise WorkflowPersistenceError(
            f"Workflow output directory does not exist: {destination.parent}"
        )
    payload = workflow_to_dict(workflow)
    try:
        destination.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except OSError as error:
        raise WorkflowPersistenceError(
            f"Could not save workflow to '{destination}': {error}"
        ) from error
    return destination.resolve()


def load_workflow(path: str | Path, registry: NodeRegistry) -> WorkflowGraph:
    """Load and validate a workflow JSON file against the available node registry."""
    source = Path(path).expanduser()
    try:
        content = source.read_text(encoding="utf-8")
    except OSError as error:
        raise WorkflowPersistenceError(
            f"Could not read workflow from '{source}': {error}"
        ) from error
    return workflow_from_json(content, registry, source_name=str(source))


def workflow_from_json(
    content: str, registry: NodeRegistry, *, source_name: str = "workflow"
) -> WorkflowGraph:
    """Parse and validate workflow JSON received without a filesystem path."""
    if not isinstance(content, str):
        raise WorkflowPersistenceError("Workflow JSON content must be text")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise WorkflowPersistenceError(
            f"Workflow file '{source_name}' is not valid JSON: {error}"
        ) from error
    return workflow_from_dict(payload, registry)


def execute_workflow_file(
    path: str | Path,
    parameter_overrides: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    registry: NodeRegistry | None = None,
) -> WorkflowRunResult:
    """Load and execute a workflow, optionally overriding parameters by node ID."""
    if registry is None:
        from flowgraph.application.node_registry import create_node_registry

        registry = create_node_registry()
    workflow = load_workflow(path, registry)
    _apply_parameter_overrides(workflow, parameter_overrides or {})
    return WorkflowExecutor(registry).run(workflow)


def execute_workflow(
    workflow: WorkflowGraph,
    registry: NodeRegistry,
    parameter_overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> WorkflowRunResult:
    """execute a workflow, optionally overriding parameters by node ID."""
    _apply_parameter_overrides(workflow, parameter_overrides or {})
    return WorkflowExecutor(registry).run(workflow)


def _parse_node(
    raw_node: object,
    index: int,
    registry: NodeRegistry,
    *,
    version: object,
) -> NodeInstance:
    if not isinstance(raw_node, Mapping):
        raise WorkflowPersistenceError(f"Node at index {index} must be an object")
    node_id = _required_string(raw_node, "id", f"node at index {index}")
    definition_id = _required_string(raw_node, "definition_id", f"node {node_id!r}")
    if registry.get(definition_id) is None:
        raise WorkflowPersistenceError(
            f"Node {node_id!r} uses unknown definition {definition_id!r}"
        )
    parameters = raw_node.get("parameters", {})
    if not isinstance(parameters, Mapping) or not all(isinstance(name, str) for name in parameters):
        raise WorkflowPersistenceError(
            f"Parameters for node {node_id!r} must be an object with string keys"
        )
    position = raw_node.get("position", {})
    if not isinstance(position, Mapping):
        raise WorkflowPersistenceError(f"Position for node {node_id!r} must be an object")
    x = _coordinate(position.get("x", 0), node_id, "x")
    y = _coordinate(position.get("y", 0), node_id, "y")
    subworkflow_payload = raw_node.get("subworkflow")
    subworkflow: WorkflowGraph | None = None
    if subworkflow_payload is not None:
        if not isinstance(subworkflow_payload, Mapping):
            raise WorkflowPersistenceError(f"Subworkflow for node {node_id!r} must be an object")
        subworkflow = workflow_from_dict(subworkflow_payload, registry)
    elif definition_id == "run-workflow" and version == LEGACY_WORKFLOW_FORMAT_VERSION:
        legacy_content = parameters.get("workflow")
        if isinstance(legacy_content, str) and legacy_content.strip():
            subworkflow = workflow_from_json(
                legacy_content,
                registry,
                source_name=f"legacy nested workflow in node {node_id!r}",
            )
        parameters = {name: value for name, value in parameters.items() if name != "workflow"}
    elif (definition := registry.get(definition_id)) is not None and definition.subworkflow_factory:
        subworkflow = definition.subworkflow_factory()
    return NodeInstance(node_id, definition_id, deepcopy(dict(parameters)), x, y, subworkflow)


def _resolve_testdata_paths(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Resolve the portable ``{testdata}`` token in persisted string values.

    The token is intentionally expanded while loading rather than while saving:
    workflow JSON remains portable and can still be edited or shared, while
    packaged demo workflows refer to the test data installed with FlowGraph.
    """
    testdata_root = package_resource_path("testdata")
    resolved = deepcopy(dict(payload))
    nodes = resolved.get("nodes")
    if not isinstance(nodes, list):
        return resolved
    for node in nodes:
        if not isinstance(node, dict):
            continue
        parameters = node.get("parameters")
        if isinstance(parameters, dict):
            node["parameters"] = {
                name: _resolve_testdata_value(value, testdata_root)
                for name, value in parameters.items()
            }
        subworkflow = node.get("subworkflow")
        if isinstance(subworkflow, Mapping):
            node["subworkflow"] = _resolve_testdata_paths(subworkflow)
    return resolved


def _resolve_testdata_value(value: Any, testdata_root: Path) -> Any:
    """Recursively resolve ``{testdata}`` in JSON-compatible parameter values."""
    if isinstance(value, str) and value.startswith("{testdata}"):
        suffix = value[len("{testdata}") :].lstrip("/\\")
        return str(testdata_root / Path(suffix))
    if isinstance(value, list):
        return [_resolve_testdata_value(item, testdata_root) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_testdata_value(item, testdata_root) for key, item in value.items()}
    return value


def _serialize_testdata_value(value: Any, testdata_root: Path) -> Any:
    """Replace packaged testdata paths with the portable ``{testdata}`` token."""
    if isinstance(value, str):
        path = Path(value).expanduser()
        try:
            relative = path.resolve().relative_to(testdata_root)
        except (OSError, ValueError):
            return value
        return "{testdata}/" + relative.as_posix()
    if isinstance(value, list):
        return [_serialize_testdata_value(item, testdata_root) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_testdata_value(item, testdata_root) for key, item in value.items()}
    return value


def _parse_workflow_port(
    raw_port: object, index: int, graph: WorkflowGraph, registry: NodeRegistry, direction: str
) -> WorkflowPort:
    if not isinstance(raw_port, Mapping):
        raise WorkflowPersistenceError(f"Workflow {direction} at index {index} must be an object")
    name = _required_string(raw_port, "name", f"workflow {direction} at index {index}")
    node_id = _required_string(raw_port, "node_id", f"workflow {direction} {name!r}")
    node_port = _required_string(raw_port, "node_port", f"workflow {direction} {name!r}")
    node = graph.require_node(node_id)
    definition = registry.require(node.definition_id)
    port = (
        definition.input_for_instance(node_port, node)
        if direction == "input"
        else definition.output_for_instance(node_port, node)
    )
    if port is None:
        raise WorkflowPersistenceError(
            f"Workflow {direction} {name!r} references unknown port {node_id!r}.{node_port!r}"
        )
    workflow_direction = PortDirection.INPUT if direction == "input" else PortDirection.OUTPUT
    return WorkflowPort(
        name, node_id, node_port, workflow_direction, port.data_type, None, port.is_param
    )


def _parse_edge(raw_edge: object, index: int) -> WorkflowEdge:
    if not isinstance(raw_edge, Mapping):
        raise WorkflowPersistenceError(f"Edge at index {index} must be an object")
    context = f"edge at index {index}"
    return WorkflowEdge(
        _required_string(raw_edge, "source_node", context),
        _required_string(raw_edge, "source_port", context),
        _required_string(raw_edge, "target_node", context),
        _required_string(raw_edge, "target_port", context),
    )


def _required_string(payload: Mapping[str, Any], key: str, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise WorkflowPersistenceError(f"{context.capitalize()} requires non-empty string {key!r}")
    return value


def _coordinate(value: object, node_id: str, axis: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorkflowPersistenceError(f"Position {axis!r} for node {node_id!r} must be a number")
    return value


def _apply_parameter_overrides(
    workflow: WorkflowGraph, overrides: Mapping[str, Mapping[str, Any]]
) -> None:
    if not isinstance(overrides, Mapping):
        raise WorkflowPersistenceError("Parameter overrides must be a mapping by node ID")
    for node_id, parameters in overrides.items():
        if not isinstance(node_id, str):
            raise WorkflowPersistenceError("Parameter override node IDs must be strings")
        node = workflow.get_node(node_id)
        if node is None:
            raise WorkflowPersistenceError(
                f"Parameter overrides reference unknown node {node_id!r}"
            )
        if not isinstance(parameters, Mapping) or not all(
            isinstance(name, str) for name in parameters
        ):
            raise WorkflowPersistenceError(
                f"Parameter overrides for node {node_id!r} must be a mapping with string keys"
            )
        node.parameters.update(deepcopy(dict(parameters)))
