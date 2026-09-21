"""JSON execution boundary for the browser-hosted FlowGraph WASM runtime."""

from __future__ import annotations

import json
from base64 import b64encode
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL.Image import Image

from flowgraph.application.wasm_node_registry import create_wasm_node_registry
from flowgraph.application.workflow_cli import format_workflow_inspection, workflow_outputs
from flowgraph.application.workflow_core import (
    NodeExecutionError,
    WorkflowError,
    WorkflowExecutor,
    WorkflowRunResult,
)
from flowgraph.application.workflow_io import workflow_from_json

_REGISTRY = None


def execute_workflow_json(workflow_json: str) -> str:
    """Execute one workflow JSON document and return a serialized response.

    The function is independent from JavaScript and is the stable Python-side
    entry point used by the persistent browser WASM worker. Runtime libraries
    may remain warm in the surrounding WASM process while workflow state is
    reconstructed for each request.
    """
    try:
        global _REGISTRY
        if _REGISTRY is None:
            _REGISTRY = create_wasm_node_registry()
        registry = _REGISTRY
        workflow = workflow_from_json(workflow_json, registry, source_name="WASM workflow")
        result = WorkflowExecutor(registry).run(workflow)
        response = {
            "status": "ok",
            "execution_order": list(result.execution_order),
            "outputs": _json_safe(workflow_outputs(workflow, result)),
            "nodes": _serialize_result(result),
            "display_inputs": _display_result(result.node_inputs),
            "display_images": _display_images(result.node_inputs),
            "projection": format_workflow_inspection(workflow, registry),
        }
    except Exception as error:  # noqa: BLE001 - the worker boundary serializes all failures
        response = _error_response(error)
    return json.dumps(response, ensure_ascii=False, separators=(",", ":"))


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


def _error_response(error: Exception) -> dict[str, Any]:
    """Convert an execution or validation failure into a stable response."""
    response: dict[str, Any] = {
        "status": "error",
        "error": {"type": type(error).__name__, "message": str(error)},
    }
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
