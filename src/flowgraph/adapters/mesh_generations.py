"""Workflow nodes that read external data into FlowGraph domain objects."""

import logging
from collections.abc import Mapping
from typing import Any

from Muscat.MeshContainers.Mesh import Mesh

from flowgraph.adapters.data_types import VEC3DSTR
from flowgraph.adapters.readers import MESH_DOCUMENT, TABLE_DOCUMENT
from flowgraph.application.workflow_core import (
    NodeDefinition,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
)
from flowgraph.domain.mesh_document import MeshDocument

LOGGER = logging.getLogger(__name__)


def create_mesh_from_table(
    inputs: Mapping[str, Any], parameters: Mapping[str, Any]
) -> Mapping[str, Any]:
    import numpy as np

    data_table = inputs["table"]
    values = parameters["value"]

    positions = np.vstack(tuple(data_table[x].flatten() for x in values)).T

    mesh = Mesh()
    mesh.SetNodes(positions, generateOriginalIDs=True)
    mesh.nodeFields = {x: data_table[x] for x in values}

    return {"mesh": MeshDocument(mesh=mesh)}


CSV_TO_MESH = NodeDefinition(
    id="csv-to-mesh",
    icon="mdi-table-merge-cells",
    label="Table to Mesh",
    description="Create a mesh from a table.",
    ports=(
        PortDefinition("table", PortDirection.INPUT, TABLE_DOCUMENT, "Table"),
        PortDefinition("mesh", PortDirection.OUTPUT, MESH_DOCUMENT, "Mesh"),
    ),
    executor=create_mesh_from_table,
    parameters=(
        ParameterDefinition(
            "value",
            VEC3DSTR,
            "Coordinates Names",
            ["x", "y", "z"],
            port=True,
        ),
    ),
)
