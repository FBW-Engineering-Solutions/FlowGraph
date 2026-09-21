"""Tests for the Python-owned Web-editor catalog exporter."""

from __future__ import annotations

import json
from pathlib import Path

from flowgraph.adapters import ADAPTERS
from flowgraph.application.workflow_io import WORKFLOW_FORMAT, WORKFLOW_FORMAT_VERSION
from flowgraph.application.workflow_web_catalog import (
    WEB_CATALOG_FORMAT,
    WEB_CATALOG_VERSION,
    workflow_web_catalog,
    write_workflow_web_catalog,
)


def _nodes(groups: list[dict[str, object]]) -> list[dict[str, object]]:
    """Flatten serialized catalog groups for concise assertions."""
    result: list[dict[str, object]] = []
    for group in groups:
        result.extend(group["nodes"])  # type: ignore[arg-type]
        result.extend(_nodes(group["subgroups"]))  # type: ignore[arg-type]
    return result


def test_workflow_web_catalog_exports_registered_nodes_without_executors() -> None:
    catalog = workflow_web_catalog()
    nodes = _nodes(catalog["groups"])

    assert catalog["format"] == WEB_CATALOG_FORMAT
    assert catalog["version"] == WEB_CATALOG_VERSION
    assert catalog["workflow_format"] == WORKFLOW_FORMAT
    assert catalog["workflow_format_version"] == WORKFLOW_FORMAT_VERSION
    assert [node["id"] for node in nodes] == [
        definition.id for definition in ADAPTERS.node_definitions
    ]
    assert all("executor" not in node for node in nodes)
    assert all("python_type" not in port for node in nodes for port in node["ports"])


def test_write_workflow_web_catalog_is_deterministic_json(tmp_path: Path) -> None:
    destination = tmp_path / "node-catalog.json"

    written = write_workflow_web_catalog(destination)

    assert written == destination.resolve()
    assert destination.read_text(encoding="utf-8") == (
        json.dumps(workflow_web_catalog(), indent=2, sort_keys=True) + "\n"
    )
