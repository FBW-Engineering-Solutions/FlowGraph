"""Tests for the Python-owned Web-editor catalog exporter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowgraph.adapters import ADAPTERS, AdapterGroup
from flowgraph.adapters.simple_sources import SET_INT
from flowgraph.application.workflow_core import NodeDefinition
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
    assert all(
        node["requirements"] == list(definition.requirements)
        for node, definition in zip(nodes, ADAPTERS.node_definitions, strict=True)
    )


def test_workflow_web_catalog_exports_direct_requirements_for_all_nodes() -> None:
    nodes = {node["id"]: node for node in _nodes(workflow_web_catalog()["groups"])}

    assert len(nodes) == len(ADAPTERS.node_definitions) == 82
    assert all(isinstance(node["requirements"], list) for node in nodes.values())
    assert all(
        isinstance(requirement, str)
        and requirement.split(":", 1)[0] in {"py", "native", "os"}
        and requirement.split(":", 1)[-1]
        for node in nodes.values()
        for requirement in node["requirements"]
    )
    assert nodes["set-string"]["requirements"] == []
    assert nodes["download-url"]["requirements"] == []
    assert nodes["run-workflow"]["requirements"] == []
    assert nodes["remesh"]["requirements"] == ["py:muscat"]
    assert nodes["load-meshio"]["requirements"] == ["py:muscat", "py:meshio"]
    assert nodes["read-table"]["requirements"] == ["py:pandas", "py:openpyxl"]
    assert nodes["image-fluency-metrics"]["requirements"] == ["py:pillow", "py:numpy"]
    assert nodes["delaunay-3d"]["requirements"] == ["py:muscat", "py:numpy", "py:scipy"]
    assert nodes["imagej-script"]["requirements"] == ["py:pyimagej", "py:numpy"]
    assert nodes["cosapp-workflow"]["requirements"] == ["py:cosapp"]
    assert nodes["extract-plaid-time-step"]["requirements"] == [
        "py:pyplaid",
        "py:muscat",
        "py:pycgns",
    ]


def test_workflow_web_catalog_exports_mesh_to_table_with_internal_selector() -> None:
    nodes = {node["id"]: node for node in _nodes(workflow_web_catalog()["groups"])}
    node = nodes["mesh-to-table"]

    assert [(port["name"], port["direction"], port["data_type_id"]) for port in node["ports"]] == [
        ("mesh", "input", "mesh-document"),
        ("table", "output", "table-document"),
    ]
    assert node["parameters"][0]["name"] == "entity"
    assert node["parameters"][0]["default"] == "node"
    assert node["parameters"][0]["port"] is False
    assert [option["value"] for option in node["parameters"][0]["options"]] == [
        "node",
        "cell",
    ]


def test_workflow_web_catalog_exports_boolean_input() -> None:
    nodes = {node["id"]: node for node in _nodes(workflow_web_catalog()["groups"])}
    node = nodes["set-boolean"]

    assert node["label"] == "Boolean Input"
    assert node["requirements"] == []
    assert [(port["name"], port["direction"], port["data_type_id"]) for port in node["ports"]] == [
        ("value", "output", "boolean"),
        ("value", "input", "boolean"),
    ]
    assert node["parameters"][0]["kind_id"] == "boolean"
    assert node["parameters"][0]["default"] is False
    assert node["parameters"][0]["port"] is True


def test_workflow_web_catalog_exports_2d_vector_input() -> None:
    nodes = {node["id"]: node for node in _nodes(workflow_web_catalog()["groups"])}
    node = nodes["set-vec2d"]

    assert node["label"] == "2D Vector Input"
    assert node["requirements"] == []
    assert [(port["name"], port["direction"], port["data_type_id"]) for port in node["ports"]] == [
        ("value", "output", "VEC2D"),
        ("x", "input", "float"),
        ("y", "input", "float"),
    ]
    assert [(param["name"], param["default"]) for param in node["parameters"]] == [
        ("x", 0.0),
        ("y", 0.0),
    ]


def test_workflow_web_catalog_exports_2d_integer_vector_input() -> None:
    nodes = {node["id"]: node for node in _nodes(workflow_web_catalog()["groups"])}
    node = nodes["set-vec2di"]

    assert node["label"] == "2D Integer Vector Input"
    assert node["requirements"] == []
    assert [(port["name"], port["direction"], port["data_type_id"]) for port in node["ports"]] == [
        ("value", "output", "VEC2DI"),
        ("x", "input", "integer"),
        ("y", "input", "integer"),
    ]
    assert [(param["name"], param["default"]) for param in node["parameters"]] == [
        ("x", 0),
        ("y", 0),
    ]
    dimension_port = next(
        port for port in nodes["create-square"]["ports"] if port["name"] == "dimensions"
    )
    assert dimension_port["data_type_id"] == "VEC2DI"


def test_write_workflow_web_catalog_is_deterministic_json(tmp_path: Path) -> None:
    destination = tmp_path / "node-catalog.json"

    written = write_workflow_web_catalog(destination)

    assert written == destination.resolve()
    assert destination.read_text(encoding="utf-8") == (
        json.dumps(workflow_web_catalog(), indent=2, sort_keys=True) + "\n"
    )


def test_extra_groups_export_custom_metadata_without_executors(tmp_path: Path) -> None:
    custom = NodeDefinition(
        id="custom-int",
        icon="mdi-numeric",
        label="Custom Integer",
        description="A user-defined integer source.",
        ports=tuple(port for port in SET_INT.ports if not port.is_param),
        executor=SET_INT.executor,
        parameters=SET_INT.parameters,
    )
    group = AdapterGroup("My Nodes", subgroups=(AdapterGroup("Numbers", (custom,)),))
    destination = tmp_path / "node-catalog.json"
    write_workflow_web_catalog(destination, extra_groups=(group,))
    exported = json.loads(destination.read_text(encoding="utf-8"))

    assert exported["groups"][:-1] == workflow_web_catalog()["groups"]
    assert exported["groups"][-1]["label"] == "My Nodes"
    node = exported["groups"][-1]["subgroups"][0]["nodes"][0]
    assert node["id"] == "custom-int"
    built_in_int = next(
        node for node in _nodes(workflow_web_catalog()["groups"]) if node["id"] == "set-int"
    )
    assert node["ports"] == built_in_int["ports"]
    assert "executor" not in node


def test_extra_groups_reject_duplicate_built_in_ids(tmp_path: Path) -> None:
    destination = tmp_path / "node-catalog.json"
    with pytest.raises(ValueError, match="Duplicate web catalog node definition: 'set-int'"):
        write_workflow_web_catalog(
            destination,
            extra_groups=(AdapterGroup("Extra", subgroups=(AdapterGroup("Nested", (SET_INT,)),)),),
        )
    assert not destination.exists()


def test_workflow_web_catalog_exports_expandable_port_capacity() -> None:
    nodes = _nodes(workflow_web_catalog()["groups"])
    aggregate = next(node for node in nodes if node["id"] == "aggregate-lists-to-table")

    assert aggregate["ports"] == [
        {
            "name": "column",
            "label": "Column",
            "direction": "input",
            "data_type_id": "list[any]",
            "data_type_label": "List Any",
            "required": False,
            "is_param": False,
            "expandable": 128,
        },
        {
            "name": "table",
            "label": "Table",
            "direction": "output",
            "data_type_id": "table-document",
            "data_type_label": "Table",
            "required": True,
            "is_param": False,
            "expandable": 0,
        },
    ]


def test_workflow_web_catalog_exports_plot_table_sink() -> None:
    nodes = _nodes(workflow_web_catalog()["groups"])
    plot_table = next(node for node in nodes if node["id"] == "plot-table")

    assert plot_table["label"] == "Plot Table"
    assert plot_table["presentation"] == "plot-table"
    assert plot_table["ports"] == [
        {
            "name": "table",
            "label": "Table",
            "direction": "input",
            "data_type_id": "table-document",
            "data_type_label": "Table",
            "required": True,
            "is_param": False,
            "expandable": 0,
        },
    ]
