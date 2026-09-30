"""Workflow nodes for constructing and transforming table documents."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from flowgraph.application.workflow_core import (
    ExecContext,
    NodeDefinition,
    NodeInstance,
    NodeRegistry,
    PortDefinition,
    PortDirection,
    WorkflowEdge,
)

from .data_types import LIST_ANY, TABLE_DOCUMENT


def _aggregate_lists_to_table(
    _instance: NodeInstance,
    inputs: Mapping[str, Any],
    _parameters: Mapping[str, Any],
    _registry: NodeRegistry,
    input_edges: Mapping[str, WorkflowEdge],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Create a table whose columns are named after connected source output ports."""
    table: dict[str, list[Any]] = {}
    for input_name, edge in input_edges.items():
        column_name = edge.source_port
        if column_name in table:
            raise ValueError(
                f"Duplicate table column name {column_name!r}; source output names must be unique"
            )
        value = inputs[input_name]
        if not isinstance(value, list):
            raise TypeError(f"Input {input_name!r} must be a list")
        table[column_name] = value
    if not table:
        raise ValueError("At least one list input must be connected")
    lengths = {len(value) for value in table.values()}
    if len(lengths) != 1:
        raise ValueError("All aggregated lists must have the same length")
    return {"table": table}


AGGREGATE_LISTS_TO_TABLE = NodeDefinition(
    id="aggregate-lists-to-table",
    requirements=(),
    icon="mdi-file-table-outline",
    label="Aggregate Lists to Table",
    description="Aggregates connected lists into table columns named after their source outputs.",
    ports=(
        PortDefinition(
            "column",
            PortDirection.INPUT,
            LIST_ANY,
            "Column",
            required=False,
            expandable=128,
        ),
        PortDefinition("table", PortDirection.OUTPUT, TABLE_DOCUMENT, "Table"),
    ),
    executor=lambda _inputs, _parameters, _exec_context: {},
    edge_aware_instance_executor=_aggregate_lists_to_table,
)

AVAILABLE_NODES = (AGGREGATE_LISTS_TO_TABLE,)

__all__ = ["AGGREGATE_LISTS_TO_TABLE", "AVAILABLE_NODES"]
