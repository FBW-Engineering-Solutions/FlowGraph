"""Workflow nodes for transferring fields between meshes."""

from collections.abc import Mapping
from typing import Any

import numpy as np
from Muscat.FE.DofNumbering import ComputeDofNumbering
from Muscat.FE.Fields.FEField import FEField
from Muscat.FE.Spaces.FESpaces import LagrangeSpaceP0
from Muscat.MeshContainers.Filters.FilterObjects import ElementFilter
from Muscat.MeshContainers.Mesh import Mesh
from Muscat.MeshTools.MeshFieldOperations import GetFieldTransferOp
from Muscat.MeshTools.MeshTools import GetElementsCenters

from flowgraph.adapters.data_types import MESH_DOCUMENT
from flowgraph.application.workflow_core import (
    NodeDefinition,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
)
from flowgraph.domain.mesh_document import MeshDocument

from .data_types import ParameterKind


def _transfer_fields(
    inputs: Mapping[str, Any], _parameters: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Transfer all nodal fields from ``source_data`` onto ``target``."""
    source_mesh: Mesh = inputs["source_data"].mesh
    target_mesh: Mesh = inputs["target"].mesh
    outpout_mesh = target_mesh.View()

    transfer_nodes = _parameters.get("transferNodeData", True)
    transfer_elements = _parameters.get("transferElementData", True)
    transfer_nodes_tags = _parameters.get("transferNodeTags", True)
    transfer_elements_tags = _parameters.get("transferElementTags", True)

    if transfer_nodes or transfer_nodes_tags:
        field = FEField(name="source", mesh=source_mesh)
        operator_nodal, _, _ = GetFieldTransferOp(field, target_mesh.nodes)
        if transfer_nodes and source_mesh.nodeFields:
            for name, data in source_mesh.nodeFields.items():
                if name == "flowgraph_node_id" or np.issubdtype(data.dtype, np.str_):
                    continue
                outpout_mesh.nodeFields[name] = np.ascontiguousarray(
                    (operator_nodal @ data).astype(data.dtype, copy=False)
                )

        if transfer_nodes_tags:
            mask = np.zeros(source_mesh.GetNumberOfNodes())
            for tag in source_mesh.nodesTags:
                mask.fill(0)
                ids = tag.GetIds()
                mask[ids] = 1

                outpout_mesh.nodesTags.CreateTag(tag.name, False).SetIds(
                    np.where(operator_nodal.dot(mask) >= 0.999999999)[0], tag.name
                )

    if transfer_elements or transfer_elements_tags:
        numbering = ComputeDofNumbering(source_mesh, LagrangeSpaceP0)
        field = FEField(name="source", mesh=source_mesh, space=LagrangeSpaceP0, numbering=numbering)
        operator_elem, _, _ = GetFieldTransferOp(
            field, GetElementsCenters(target_mesh), elementFilter=ElementFilter()
        )

        if transfer_elements and source_mesh.elemFields:
            for name, data in source_mesh.elemFields.items():
                if name == "flowgraph_element_id" or np.issubdtype(data.dtype, np.str_):
                    continue
                outpout_mesh.elemFields[name] = np.ascontiguousarray(
                    (operator_elem @ data).astype(data.dtype, copy=False)
                )

        if transfer_elements_tags:
            mask = np.zeros(source_mesh.GetNumberOfElements())
            for tagname in source_mesh.elements.GetTagsNames():
                mask.fill(0)
                ids = source_mesh.GetElementsInTag(tagname)
                mask[ids] = 1

                outpout_mesh.AddElementsToTag(np.where(operator_elem.dot(mask))[0], tagname)

    return {"mesh_document": MeshDocument(outpout_mesh)}


TRANSFER_FIELDS_NODE = NodeDefinition(
    id="transfer-fields",
    icon="mdi-swap-horizontal-bold",
    label="Transfer Fields",
    description="Transfers nodal fields from one mesh onto another mesh.",
    ports=(
        PortDefinition("source_data", PortDirection.INPUT, MESH_DOCUMENT, "Source data"),
        PortDefinition("target", PortDirection.INPUT, MESH_DOCUMENT, "Target"),
        PortDefinition("mesh_document", PortDirection.OUTPUT, MESH_DOCUMENT, "Mesh document"),
    ),
    parameters=(
        ParameterDefinition(
            "transferNodeData", ParameterKind.BOOLEAN, "Apply on node fields", True, port=False
        ),
        ParameterDefinition(
            "transferElementData",
            ParameterKind.BOOLEAN,
            "Apply on element fields",
            True,
            port=False,
        ),
        ParameterDefinition(
            "transferNodeTags", ParameterKind.BOOLEAN, "Transfer Node Tags", False, port=False
        ),
        ParameterDefinition(
            "transferElementTags", ParameterKind.BOOLEAN, "Transfer Element Tags", False, port=False
        ),
    ),
    executor=_transfer_fields,
)


AVAILABLE_NODES = (TRANSFER_FIELDS_NODE,)
