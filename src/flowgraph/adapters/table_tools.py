"""Workflow nodes for constructing and transforming table documents."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from flowgraph.application.workflow_core import (
    ExecContext,
    NodeDefinition,
    NodeInstance,
    NodeRegistry,
    ParameterDefinition,
    ParameterOption,
    PortDefinition,
    PortDirection,
    WorkflowEdge,
)
from flowgraph.domain.mesh_document import MeshDocument

from .data_types import LIST_ANY, MESH_DOCUMENT, TABLE_DOCUMENT, ParameterKind


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


def _mesh_to_table(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Copy node or cell fields into a table with one row per mesh entity."""
    document: MeshDocument = inputs["mesh"]
    entity = parameters.get("entity", "node")
    if entity == "node":
        fields = document.mesh.nodeFields
        count = document.mesh.GetNumberOfNodes()
    elif entity == "cell":
        fields = document.mesh.elemFields
        count = document.mesh.GetNumberOfElements()
    else:
        raise ValueError(f"entity must be 'node' or 'cell', got {entity!r}")

    table: dict[str, list[Any]] = {}
    for name, field in fields.items():
        values = np.asarray(field)
        if values.ndim == 0 or len(values) != count:
            raise ValueError(f"{entity} field {name!r} must have {count} rows")
        table[name] = values.tolist()
    return {"table": table}


MESH_TO_TABLE = NodeDefinition(
    id="mesh-to-table",
    requirements=("py:muscat", "py:numpy"),
    icon="mdi-table-arrow-right",
    label="Mesh to Table",
    description="Copy node or cell fields from a mesh document into a table.",
    ports=(
        PortDefinition("mesh", PortDirection.INPUT, MESH_DOCUMENT, "Mesh"),
        PortDefinition("table", PortDirection.OUTPUT, TABLE_DOCUMENT, "Table"),
    ),
    executor=_mesh_to_table,
    parameters=(
        ParameterDefinition(
            "entity",
            ParameterKind.STR_SELECT,
            "Data location",
            "node",
            options=(ParameterOption("node", "Node data"), ParameterOption("cell", "Cell data")),
            port=False,
        ),
    ),
)


AVAILABLE_NODES = (AGGREGATE_LISTS_TO_TABLE, MESH_TO_TABLE)

__all__ = ["AGGREGATE_LISTS_TO_TABLE", "AVAILABLE_NODES", "MESH_TO_TABLE"]
