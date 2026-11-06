"""Send workflow datasets to the persistent ParaView Live gateway."""

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
)
from flowgraph.paraview_gateway import data_transaction, send_dataset, to_vtk

from .data_types import FLOAT, IMAGE, INTEGER, MESH_DOCUMENT, STRING, TABLE_DOCUMENT


def SendMeshToParaView(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Send connected datasets; direct callers must supply ``node_id``."""
    node_id = parameters.get("node_id")
    if not isinstance(node_id, str) or not node_id:
        raise ValueError("ParaView bridge requires a nonempty node instance ID")
    selected = []
    for kind in ("mesh", "table", "image"):
        for index in range(1, 11):
            name = f"{kind}_{index}"
            if name in inputs:
                selected.append((name, kind, inputs[name]))
    connection = {
        "host": parameters.get("host", "127.0.0.1"),
        "port": parameters.get("port", 33333),
        "timeout": parameters.get("timeout", 10.0),
    }
    with data_transaction(node_id, **connection) as transaction_id:
        for name, kind, value in selected:
            send_dataset(
                node_id,
                kind,
                to_vtk(kind, value),
                **connection,
                input_name=name,
                transaction_id=transaction_id,
            )
    return {}


def _send_instance(
    instance: NodeInstance,
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _registry: NodeRegistry,
    exec_context: ExecContext,
) -> Mapping[str, Any]:
    """Use graph identity rather than an editable parameter for source names."""
    return SendMeshToParaView(inputs, {**parameters, "node_id": instance.id}, exec_context)


PARAVIEW_BRIDGE = NodeDefinition(
    cache_policy="always",
    id="paraview-bridge",
    requirements=("py:vtk", "py:numpy"),
    icon="mdi-file-export-outline",
    label="Send to ParaView",
    description="Sends meshes, tables and images to a persistent ParaView Live gateway.",
    ports=(
        PortDefinition(
            "mesh",
            PortDirection.INPUT,
            MESH_DOCUMENT,
            "Mesh",
            required=False,
            expandable=10,
        ),
        PortDefinition(
            "table",
            PortDirection.INPUT,
            TABLE_DOCUMENT,
            "Table",
            required=False,
            expandable=10,
        ),
        PortDefinition(
            "image",
            PortDirection.INPUT,
            IMAGE,
            "Image",
            required=False,
            expandable=10,
        ),
    ),
    parameters=(
        ParameterDefinition("host", STRING, "Gateway host", "127.0.0.1", port=False),
        ParameterDefinition("port", INTEGER, "Gateway port", 33333, port=False),
        ParameterDefinition("timeout", FLOAT, "Timeout (seconds)", 10.0, port=False),
    ),
    executor=SendMeshToParaView,
    instance_executor=_send_instance,
)

# Spelling used by the original bridge prototype.
PARAIEW_BRIDGE = PARAVIEW_BRIDGE
