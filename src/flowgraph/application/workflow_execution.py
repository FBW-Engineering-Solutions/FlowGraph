"""Transport-independent JSON workflow execution and result serialization."""

from __future__ import annotations

import json
import math
import traceback
from base64 import b64encode
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from Muscat.MeshTools.MeshInspectionTools import ExtractElementsByElementFilter
from Muscat.MeshTools.MeshModificationTools import ComputeSkin
from Muscat.MeshTools.MeshTetrahedrization import Tetrahedrization
from Muscat.Simple import ED, ElementFilter
from PIL.Image import Image

from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_cli import (
    format_workflow_inspection,
    resolve_workflow_inputs,
    workflow_outputs,
)
from flowgraph.application.workflow_core import (
    NodeExecutionError,
    WorkflowError,
    WorkflowExecutor,
    WorkflowRunResult,
)
from flowgraph.application.workflow_io import workflow_from_json
from flowgraph.domain.mesh_document import MeshDocument

_REGISTRY = None


def execute_workflow_json(workflow_json: str) -> str:
    """Execute one workflow JSON document and return a serialized response.

    Native Python clients and browser-hosted Python workers share this entry
    point. The node registry is cached within the calling process, while workflow
    state is reconstructed for each request. Process management, cancellation,
    authentication, and workspace configuration belong to the calling transport.
    Non-finite numbers are transported as JSON null; Python-text displays retain
    their original representations. Runtime values used by nodes are not changed.
    """
    warnings: list[str] = []
    try:
        global _REGISTRY
        if _REGISTRY is None:
            _REGISTRY = create_node_registry()
        registry = _REGISTRY
        workflow = workflow_from_json(workflow_json, registry, source_name="Workflow execution")
        injected = resolve_workflow_inputs(workflow, {}, on_warning=warnings.append)
        result = WorkflowExecutor(registry).run(workflow, initial_inputs=injected)
        response = {
            "status": "ok",
            "execution_order": list(result.execution_order),
            "outputs": _json_safe(workflow_outputs(workflow, result)),
            "nodes": _serialize_result(result),
            "display_inputs": _display_result(result.node_inputs),
            "display_images": _display_images(result.node_inputs),
            "display_meshes": _display_meshes(workflow, result.node_inputs),
            "projection": format_workflow_inspection(workflow, registry),
        }
    except Exception as error:  # noqa: BLE001 - the execution boundary serializes all failures
        response = _error_response(error)
    response["warnings"] = warnings
    return json.dumps(
        _json_safe(response), ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def _serialize_result(result: WorkflowRunResult) -> dict[str, Any]:
    """Return JSON-safe retained inputs and outputs for one execution result."""
    return {
        "inputs": _json_safe(result.node_inputs),
        "outputs": _json_safe(result.node_outputs),
    }


def _display_result(values: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    """Return Python string representations for values shown in the web editor."""
    return {
        str(node_id): {str(port_name): str(value) for port_name, value in node_values.items()}
        for node_id, node_values in values.items()
    }


def _display_images(
    values: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Return browser-ready PNG previews for Pillow image inputs."""
    previews: dict[str, dict[str, dict[str, Any]]] = {}
    for node_id, node_values in values.items():
        node_previews: dict[str, dict[str, Any]] = {}
        for port_name, value in node_values.items():
            if not isinstance(value, Image):
                continue
            buffer = BytesIO()
            value.save(buffer, format="PNG")
            node_previews[str(port_name)] = {
                "mime_type": "image/png",
                "data": b64encode(buffer.getvalue()).decode("ascii"),
                "width": value.width,
                "height": value.height,
                "mode": value.mode,
            }
        if node_previews:
            previews[str(node_id)] = node_previews
    return previews


def _surface_cell_fields(mesh: Any, surface: Any) -> dict[str, np.ndarray]:
    """Map surface cells to source elements, including newly extracted volume faces."""
    owners = {}
    offset = 0
    # Prefer explicit surface elements over their adjacent volume elements.
    for elements in mesh.elements.values():
        if ED.dimensionality[elements.elementType] == 2:
            for index, connectivity in enumerate(elements.connectivity):
                owners[tuple(sorted(connectivity))] = offset + index
        offset += elements.GetNumberOfElements()
    offset = 0
    for elements in mesh.elements.values():
        if ED.dimensionality[elements.elementType] == 3:
            for _, local_face in ED.faces1[elements.elementType]:
                for index, connectivity in enumerate(elements.connectivity[:, local_face]):
                    owners.setdefault(tuple(sorted(connectivity)), offset + index)
        offset += elements.GetNumberOfElements()
    indices = np.asarray(
        [
            owners.get(tuple(sorted(surface.originalIDNodes[connectivity])), -1)
            for elements in surface.elements.values()
            for connectivity in elements.connectivity
        ]
    )
    if np.any(indices < 0):
        return {}
    fields = {}
    for name, data in mesh.elemFields.items():
        array = np.asarray(data)
        if (
            array.ndim not in (1, 2)
            or len(array) != mesh.GetNumberOfElements()
            or not np.issubdtype(array.dtype, np.number)
            or np.issubdtype(array.dtype, np.complexfloating)
        ):
            continue
        if array.ndim == 2:
            if not array.shape[1]:
                continue
            if array.shape[1] == 1:
                array = array[:, 0]
        if np.all(np.isfinite(array[indices])):
            fields[name] = array[indices]
    return fields


def _display_meshes(workflow: Any, values: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Project only 3D-view sink inputs into Plotly-ready surface triangles."""
    previews: dict[str, Any] = {}
    for node in workflow.nodes:
        if node.definition_id != "mesh-sink":
            continue
        document = values.get(node.id, {}).get("mesh")
        if not isinstance(document, MeshDocument):
            continue
        try:
            mesh = document.mesh
            # Work on a view; neither skin extraction nor triangulation may mutate the input.
            surface = mesh.View()
            surface.elemFields = {}
            ComputeSkin(mesh=surface, inPlace=True)
            surface = ExtractElementsByElementFilter(
                surface, ElementFilter(dimensionality=2), copy=False
            )
            surface.elemFields = _surface_cell_fields(mesh, surface)
            triangles = Tetrahedrization(surface)
            faces = triangles.GetElementsOfType(ED.Triangle_3).connectivity
            if not faces.size:
                previews[node.id] = {"error": "The mesh has no renderable surface triangles."}
                continue

            points = triangles.nodes
            preview: dict[str, Any] = {
                "x": points[:, 0].tolist(),
                "y": points[:, 1].tolist(),
                "z": (points[:, 2] if points.shape[1] > 2 else np.zeros(len(points))).tolist(),
                "i": faces[:, 0].tolist(),
                "j": faces[:, 1].tolist(),
                "k": faces[:, 2].tolist(),
                "fields": {},
                "field_components": {},
                "cell_fields": {},
                "cell_field_components": {},
            }
            for name, data in triangles.elemFields.items():
                array = np.asarray(data)
                if array.ndim == 2 and array.shape[1] > 1:
                    preview["cell_field_components"][name] = array.tolist()
                    array = np.linalg.norm(array, axis=1)
                preview["cell_fields"][name] = array.tolist()
            # Muscat's skin/triangulation does not carry nodeFields across. The
            # originalIDNodes arrays trace each output vertex back to the input mesh.
            indices = np.asarray(surface.originalIDNodes)[np.asarray(triangles.originalIDNodes)]
            for name, data in mesh.nodeFields.items():
                if name.startswith("flowgraph_"):
                    continue
                array = np.asarray(data)
                if (
                    array.ndim == 0
                    or array.shape[0] != mesh.GetNumberOfNodes()
                    or not np.issubdtype(array.dtype, np.number)
                    or np.issubdtype(array.dtype, np.complexfloating)
                ):
                    continue
                if array.ndim == 1:
                    scalar = array
                elif array.ndim == 2 and array.shape[1] >= 1:
                    scalar = array[:, 0] if array.shape[1] == 1 else np.linalg.norm(array, axis=1)
                else:
                    continue
                values_for_vertices = scalar[indices]
                if np.all(np.isfinite(values_for_vertices)):
                    preview["fields"][name] = values_for_vertices.tolist()
                    if array.ndim == 2 and array.shape[1] > 1:
                        preview["field_components"][name] = array[indices].tolist()
            previews[node.id] = preview
        except Exception as error:  # noqa: BLE001 - do not fail an otherwise successful workflow
            previews[node.id] = {"error": f"Mesh preview unavailable: {error}"}
    return previews


def _error_response(error: Exception) -> dict[str, Any]:
    """Convert an execution or validation failure into a stable response."""
    response: dict[str, Any] = {
        "status": "error",
        "error": {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": "".join(traceback.format_exception(error)),
        },
    }
    if isinstance(error, NodeExecutionError):
        response["error"]["node_id"] = error.node_id
        response["error"]["definition_id"] = error.definition_id
    if isinstance(error, NodeExecutionError) and error.partial_result is not None:
        response["partial"] = _serialize_result(error.partial_result)
    if isinstance(error, WorkflowError) and getattr(error, "issues", None):
        response["error"]["issues"] = [
            {
                "code": issue.code.value,
                "message": issue.message,
                "node_id": issue.node_id,
                "edge_id": issue.edge_id,
            }
            for issue in error.issues
        ]
    return response


def _json_safe(value: Any) -> Any:
    """Convert runtime values into deterministic JSON-compatible data."""
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "mode") and hasattr(value, "size"):
        return {"type": type(value).__name__, "mode": value.mode, "size": list(value.size)}
    return {"type": type(value).__name__, "description": str(value)}


__all__ = ["execute_workflow_json"]
