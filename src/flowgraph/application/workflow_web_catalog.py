"""Export the non-executable workflow catalog consumed by the static web editor."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from flowgraph.adapters import ADAPTERS, AdapterGroup
from flowgraph.application.port_conversions import PORT_CONVERSIONS
from flowgraph.application.workflow_core import NodeDefinition, ParameterDefinition, PortDefinition
from flowgraph.application.workflow_io import WORKFLOW_FORMAT, WORKFLOW_FORMAT_VERSION

WEB_CATALOG_FORMAT = "flowgraph-web-node-catalog"
WEB_CATALOG_VERSION = 1


def workflow_web_catalog() -> dict[str, Any]:
    """Return a JSON-compatible, non-executable description of the workflow catalog.

    The result intentionally excludes node executors, port resolvers, runtime Python
    types, and all other callable behavior. A static editor may use it to author and
    structurally validate workflow JSON, but it cannot execute a workflow from it.
    """
    catalog = {
        "format": WEB_CATALOG_FORMAT,
        "version": WEB_CATALOG_VERSION,
        "workflow_format": WORKFLOW_FORMAT,
        "workflow_format_version": WORKFLOW_FORMAT_VERSION,
        "groups": [_group_to_dict(group) for group in ADAPTERS.groups],
        "conversions": [
            {
                "source_type_id": conversion.source_type_id,
                "target_type_id": conversion.target_type_id,
                "label": conversion.label,
            }
            for conversion in PORT_CONVERSIONS
        ],
    }
    _assert_json_compatible(catalog)
    return catalog


def write_workflow_web_catalog(path: str | Path) -> Path:
    """Write the deterministic static-editor catalog JSON to *path*.

    Parameters
    ----------
    path:
        Destination JSON file. Its parent directory must already exist.

    Returns
    -------
    pathlib.Path
        The resolved output path.
    """
    destination = Path(path)
    if not destination.parent.is_dir():
        raise ValueError(f"Web catalog output directory does not exist: {destination.parent}")
    destination.write_text(
        json.dumps(workflow_web_catalog(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return destination.resolve()


def _group_to_dict(group: AdapterGroup) -> dict[str, Any]:
    """Serialize an ordered catalog group and its nested groups."""
    return {
        "label": group.label,
        "nodes": [_node_to_dict(definition) for definition in group.node_definitions],
        "subgroups": [_group_to_dict(subgroup) for subgroup in group.subgroups],
    }


def _node_to_dict(definition: NodeDefinition) -> dict[str, Any]:
    """Serialize static authoring metadata for one node definition."""
    return {
        "id": definition.id,
        "icon": definition.icon,
        "label": definition.label,
        "description": definition.description,
        "color": definition.color,
        "presentation": definition.presentation,
        "ports": [_port_to_dict(port) for port in definition.ports],
        "parameters": [_parameter_to_dict(parameter) for parameter in definition.parameters],
        "creates_subworkflow": definition.subworkflow_factory is not None,
        "has_dynamic_ports": (
            definition.port_resolver is not None or definition.instance_port_resolver is not None
        ),
    }


def _port_to_dict(port: PortDefinition) -> dict[str, Any]:
    """Serialize one named typed node endpoint."""
    return {
        "name": port.name,
        "label": port.display_label,
        "direction": port.direction.value,
        "data_type_id": port.data_type.id,
        "data_type_label": port.data_type.label,
        "required": port.required,
        "is_param": port.is_param,
    }


def _parameter_to_dict(parameter: ParameterDefinition) -> dict[str, Any]:
    """Serialize one editable parameter schema without runtime type objects."""
    return {
        "name": parameter.name,
        "kind_id": parameter.kind.id,
        "kind_label": parameter.kind.label,
        "label": parameter.label,
        "default": deepcopy(parameter.default),
        "placeholder": parameter.placeholder,
        "options": [
            {"value": deepcopy(option.value), "label": option.label} for option in parameter.options
        ],
        "file_patterns": list(parameter.file_patterns),
        "port": parameter.port,
    }


def _assert_json_compatible(payload: Mapping[str, Any]) -> None:
    """Raise a useful error if a catalog implementation adds non-JSON metadata."""
    try:
        json.dumps(payload)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Workflow web catalog is not JSON-compatible: {error}") from error


def main() -> None:
    """Write the web-editor catalog to a command-line-selected JSON file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Destination node-catalog.json path.")
    args = parser.parse_args()
    print(write_workflow_web_catalog(args.output))


if __name__ == "__main__":
    main()
