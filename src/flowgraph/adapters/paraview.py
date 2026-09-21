"""Simple workflow sink to send the files to paraview."""

import json
import socket
from collections.abc import Mapping
from typing import Any

from flowgraph.adapters.readers import MESH_DOCUMENT
from flowgraph.application.workflow_core import (
    DataType,
    NodeDefinition,
    PortDefinition,
    PortDirection,
)

STRING = DataType("string", "Text", str)


def SendMeshToParaView(
    inputs: Mapping[str, Any], parameters: Mapping[str, Any]
) -> Mapping[str, Any]:

    data = {"command": "test", "value": 123}
    host = parameters.get("host", "127.0.0.1")
    port = int(parameters.get("port", 9999))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((host, port))
        sock.sendall(json.dumps(data).encode("utf-8"))
    return {}


PARAIEW_BRIDGE = NodeDefinition(
    id="write-muscat",
    icon="mdi-file-export-outline",
    label="Write with Muscat",
    description="Writes the canonical mesh document to a filename selected by extension.",
    ports=(PortDefinition("mesh", PortDirection.INPUT, MESH_DOCUMENT, "Mesh"),),
    executor=SendMeshToParaView,
)
