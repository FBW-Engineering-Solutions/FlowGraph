"""Composite node that executes an editable nested workflow graph."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from flowgraph.application.workflow_core import (
    ExecContext,
    NodeDefinition,
    NodeInstance,
    NodeRegistry,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
    WorkflowExecutor,
    WorkflowGraph,
    WorkflowRunResult,
)

from .data_types import (
    ANY,
    BOOLEAN,
    FLOAT,
    INTEGER,
    LIST_ANY,
    LIST_FLOAT,
    LIST_INT,
    LIST_STR,
    STRING,
)

RUN_WORKFLOW_PORTS = (PortDefinition("result", PortDirection.OUTPUT, ANY, "Result"),)
BATCH_WORKFLOW_PORTS = (PortDefinition("result", PortDirection.OUTPUT, LIST_ANY, "Results"),)

_BATCH_LIST_TYPES = {
    STRING.id: LIST_STR,
    INTEGER.id: LIST_INT,
    FLOAT.id: LIST_FLOAT,
}


def _nested_ports(instance: NodeInstance) -> tuple[PortDefinition, ...]:
    """Return ports exported by a composite node's child workflow."""
    graph = instance.subworkflows.get("default")
    if graph is None:
        return RUN_WORKFLOW_PORTS
    exported = tuple(
        PortDefinition(port.name, port.direction, port.data_type, port.display_label)
        for port in (*graph.inputs, *graph.outputs)
    )
    names = {(port.direction, port.name) for port in RUN_WORKFLOW_PORTS}
    return RUN_WORKFLOW_PORTS + tuple(
        port for port in exported if (port.direction, port.name) not in names
    )


def _execute_workflow(
    instance: NodeInstance,
    inputs: Mapping[str, Any],
    _parameters: Mapping[str, Any],
    registry: NodeRegistry,
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Execute the child graph with values supplied to its public inputs."""
    context = _exec_context or ExecContext()
    if set(instance.subworkflows) != {"default"}:
        raise ValueError("Run Full Workflow requires exactly the 'default' child")
    graph = instance.subworkflows.get("default")
    if graph is None:
        raise ValueError("The nested workflow is not initialized")
    graph.sync_boundary_nodes(registry)
    injected: dict[str, dict[str, Any]] = {}
    for port in graph.inputs:
        injected.setdefault(port.node_id, {})[port.node_port] = inputs[port.name]
    nested_result: WorkflowRunResult = WorkflowExecutor(
        registry,
        parallel_tasks=context.parallel_tasks,
        gpu_available=context.gpu_available,
    ).run(graph, initial_inputs=injected)
    outputs = {
        port.name: nested_result.node_outputs[port.node_id][port.node_port]
        for port in graph.outputs
    }
    return {"result": nested_result, **outputs}


def _batch_ports(instance: NodeInstance) -> tuple[PortDefinition, ...]:
    """Return broadcasting inputs and aggregated outputs of a child workflow."""
    graph = instance.subworkflows.get("default")
    if graph is None:
        return BATCH_WORKFLOW_PORTS
    inputs = tuple(
        PortDefinition(
            port.name,
            PortDirection.INPUT,
            port.data_type,
            port.display_label,
            accepted_data_types=(list_type,)
            if (list_type := _BATCH_LIST_TYPES.get(port.data_type.id))
            else (),
        )
        for port in graph.inputs
    )
    outputs = tuple(
        PortDefinition(
            port.name,
            PortDirection.OUTPUT,
            _BATCH_LIST_TYPES.get(port.data_type.id, LIST_ANY),
            port.display_label,
        )
        for port in graph.outputs
    )
    names = {(port.direction, port.name) for port in BATCH_WORKFLOW_PORTS}
    return BATCH_WORKFLOW_PORTS + tuple(
        port for port in (*inputs, *outputs) if (port.direction, port.name) not in names
    )


def _execute_batch_workflow(
    instance: NodeInstance,
    inputs: Mapping[str, Any],
    _parameters: Mapping[str, Any],
    registry: NodeRegistry,
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Execute a child graph for each list entry and aggregate its public outputs.

    Lists define the batch dimension and must all have the same length. Scalar
    inputs broadcast to every child execution.
    """
    context = _exec_context or ExecContext()
    if set(instance.subworkflows) != {"default"}:
        raise ValueError("Batch Workflow requires exactly the 'default' child")
    graph = instance.subworkflows.get("default")
    if graph is None:
        raise ValueError("The nested workflow is not initialized")
    graph.sync_boundary_nodes(registry)
    list_inputs = {name: value for name, value in inputs.items() if isinstance(value, list)}
    if not list_inputs:
        raise ValueError("Batch Workflow requires at least one list input")
    lengths = {len(value) for value in list_inputs.values()}
    if len(lengths) != 1:
        details = ", ".join(f"{name}={len(value)}" for name, value in list_inputs.items())
        raise ValueError(f"Batch Workflow list inputs must have equal lengths: {details}")

    batch_size = lengths.pop()
    results: list[WorkflowRunResult] = []
    outputs = {port.name: [] for port in graph.outputs}
    executor = WorkflowExecutor(
        registry,
        parallel_tasks=context.parallel_tasks,
        gpu_available=context.gpu_available,
    )
    for index in range(batch_size):
        injected = {
            port.node_id: {
                port.node_port: inputs[port.name][index]
                if isinstance(inputs[port.name], list)
                else inputs[port.name]
            }
            for port in graph.inputs
        }
        result = executor.run(graph, initial_inputs=injected)
        results.append(result)
        for port in graph.outputs:
            outputs[port.name].append(result.node_outputs[port.node_id][port.node_port])
    return {"result": results, **outputs}


def _empty_workflow() -> dict[str, WorkflowGraph]:
    """Create independent named children for a single-child composite."""
    return {"default": WorkflowGraph()}


RUN_WORKFLOW = NodeDefinition(
    id="run-workflow",
    requirements=(),
    icon="mdi-play-network-outline",
    label="Run Full Workflow",
    description="Executes and exports the inputs and outputs of an editable nested workflow.",
    ports=(RUN_WORKFLOW_PORTS),
    executor=lambda _inputs, _parameters, _exec_context: {},
    instance_port_resolver=_nested_ports,
    instance_executor=_execute_workflow,
    subworkflows_factory=_empty_workflow,
    presentation="workflow",
)

BATCH_WORKFLOW = NodeDefinition(
    id="batch-workflow",
    requirements=(),
    icon="mdi-format-list-numbered",
    label="Batch Workflow",
    description="Executes an editable nested workflow once for each list entry.",
    ports=(BATCH_WORKFLOW_PORTS),
    executor=lambda _inputs, _parameters, _exec_context: {},
    instance_port_resolver=_batch_ports,
    instance_executor=_execute_batch_workflow,
    subworkflows_factory=_empty_workflow,
    presentation="workflow",
)


def _conditional_children() -> dict[str, WorkflowGraph]:
    return {"false": WorkflowGraph(), "true": WorkflowGraph()}


def _conditional_interface(instance: NodeInstance) -> WorkflowGraph:
    """Validate alternatives without executing either child."""
    if set(instance.subworkflows) != {"false", "true"}:
        raise ValueError("Conditional Workflow requires exactly 'false' and 'true' children")
    false_graph = instance.subworkflows["false"]
    true_graph = instance.subworkflows["true"]
    for direction in ("inputs", "outputs"):
        left = {port.name: port.data_type for port in getattr(false_graph, direction)}
        right = {port.name: port.data_type for port in getattr(true_graph, direction)}
        if left != right:
            raise ValueError(f"Conditional Workflow branches must have matching {direction}")
    if any(port.name == "condition" for port in false_graph.inputs):
        raise ValueError("Conditional Workflow child input 'condition' is reserved")
    if any(port.name == "result" for port in false_graph.outputs):
        raise ValueError("Conditional Workflow child output 'result' is reserved")
    return false_graph


def _conditional_ports(instance: NodeInstance) -> tuple[PortDefinition, ...]:
    # Ports remain available while alternatives are being edited. Full interface
    # agreement is checked at execution, not while loading an unfinished graph.
    graph = instance.subworkflows.get("false")
    ports = (
        ()
        if graph is None
        else tuple(
            PortDefinition(port.name, port.direction, port.data_type, port.display_label)
            for port in (*graph.inputs, *graph.outputs)
            if (port.direction, port.name)
            not in {(PortDirection.INPUT, "condition"), (PortDirection.OUTPUT, "result")}
        )
    )
    return CONDITIONAL_WORKFLOW.ports + ports


def _execute_conditional(
    instance: NodeInstance,
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    registry: NodeRegistry,
    exec_context: ExecContext,
) -> Mapping[str, Any]:
    """Execute exactly one alternative and expose its common public outputs."""
    for child in instance.subworkflows.values():
        child.sync_boundary_nodes(registry)
    _conditional_interface(instance)
    condition = parameters["condition"]
    if type(condition) is not bool:
        raise TypeError("Conditional Workflow condition must be a boolean")
    graph = instance.subworkflows["true" if condition else "false"]
    selected = NodeInstance(instance.id, "run-workflow", subworkflows={"default": graph})
    return _execute_workflow(selected, inputs, parameters, registry, exec_context)


CONDITIONAL_WORKFLOW = NodeDefinition(
    id="conditional-workflow",
    icon="mdi-source-branch",
    label="Conditional Workflow",
    description="Executes only the true or false child workflow and returns its outputs.",
    ports=RUN_WORKFLOW_PORTS,
    parameters=(ParameterDefinition("condition", BOOLEAN, "Condition", False),),
    executor=lambda _inputs, _parameters, _context: {},
    instance_port_resolver=_conditional_ports,
    instance_executor=_execute_conditional,
    subworkflows_factory=_conditional_children,
    presentation="workflow",
)

AVAILABLE_NODES = (RUN_WORKFLOW, BATCH_WORKFLOW, CONDITIONAL_WORKFLOW)

__all__ = ["AVAILABLE_NODES", "BATCH_WORKFLOW", "CONDITIONAL_WORKFLOW", "RUN_WORKFLOW"]
