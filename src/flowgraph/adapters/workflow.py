"""Composite node that executes an editable nested workflow graph."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from flowgraph.application.workflow_core import (
    NodeDefinition,
    NodeInstance,
    NodeRegistry,
    PortDefinition,
    PortDirection,
    WorkflowExecutor,
    WorkflowGraph,
    WorkflowRunResult,
)

from .data_types import ANY, FLOAT, INTEGER, LIST_ANY, LIST_FLOAT, LIST_INT, LIST_STR, STRING

RUN_WORKFLOW_PORTS = (PortDefinition("result", PortDirection.OUTPUT, ANY, "Result"),)
BATCH_WORKFLOW_PORTS = (PortDefinition("result", PortDirection.OUTPUT, LIST_ANY, "Results"),)

_BATCH_LIST_TYPES = {
    STRING.id: LIST_STR,
    INTEGER.id: LIST_INT,
    FLOAT.id: LIST_FLOAT,
}


def _nested_ports(instance: NodeInstance) -> tuple[PortDefinition, ...]:
    """Return ports exported by a composite node's child workflow."""
    graph = instance.subworkflow
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
) -> Mapping[str, Any]:
    """Execute the child graph with values supplied to its public inputs."""
    graph = instance.subworkflow
    if graph is None:
        raise ValueError("The nested workflow is not initialized")
    graph.sync_boundary_nodes(registry)
    injected = {port.node_id: {port.node_port: inputs[port.name]} for port in graph.inputs}
    nested_result: WorkflowRunResult = WorkflowExecutor(registry).run(
        graph, initial_inputs=injected
    )
    outputs = {
        port.name: nested_result.node_outputs[port.node_id][port.node_port]
        for port in graph.outputs
    }
    return {"result": nested_result, **outputs}


def _batch_ports(instance: NodeInstance) -> tuple[PortDefinition, ...]:
    """Return broadcasting inputs and aggregated outputs of a child workflow."""
    graph = instance.subworkflow
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
) -> Mapping[str, Any]:
    """Execute a child graph for each list entry and aggregate its public outputs.

    Lists define the batch dimension and must all have the same length. Scalar
    inputs broadcast to every child execution.
    """
    graph = instance.subworkflow
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
    executor = WorkflowExecutor(registry)
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


def _empty_workflow() -> WorkflowGraph:
    """Create an independent empty graph for one composite node instance."""
    return WorkflowGraph()


RUN_WORKFLOW = NodeDefinition(
    id="run-workflow",
    icon="mdi-play-network-outline",
    label="Run Full Workflow",
    description="Executes and exports the inputs and outputs of an editable nested workflow.",
    ports=(RUN_WORKFLOW_PORTS),
    executor=lambda _inputs, _parameters: {},
    instance_port_resolver=_nested_ports,
    instance_executor=_execute_workflow,
    subworkflow_factory=_empty_workflow,
    presentation="workflow",
)

BATCH_WORKFLOW = NodeDefinition(
    id="batch-workflow",
    icon="mdi-format-list-numbered",
    label="Batch Workflow",
    description="Executes an editable nested workflow once for each list entry.",
    ports=(BATCH_WORKFLOW_PORTS),
    executor=lambda _inputs, _parameters: {},
    instance_port_resolver=_batch_ports,
    instance_executor=_execute_batch_workflow,
    subworkflow_factory=_empty_workflow,
    presentation="workflow",
)

AVAILABLE_NODES = (RUN_WORKFLOW, BATCH_WORKFLOW)

__all__ = ["AVAILABLE_NODES", "BATCH_WORKFLOW", "RUN_WORKFLOW"]
