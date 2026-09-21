"""Workflow boundary nodes that define public inputs and outputs."""

from collections.abc import Mapping
from typing import Any

from flowgraph.application.workflow_core import (
    NodeDefinition,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
)

from .data_types import ANY, ParameterKind


def _workflow_input(inputs: Mapping[str, Any], _parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Pass a supplied workflow input through to downstream nodes."""
    return {"value": inputs["value"]}


WORKFLOW_INPUT = NodeDefinition(
    id="workflow-input",
    icon="mdi-import",
    label="Workflow Input",
    description="Defines a named public input for the workflow.",
    ports=(
        PortDefinition("value", PortDirection.INPUT, ANY, "Value"),
        PortDefinition("value", PortDirection.OUTPUT, ANY, "Value"),
    ),
    executor=_workflow_input,
    parameters=(
        ParameterDefinition(
            "name",
            ParameterKind.TEXT,
            "Input name",
            "input",
            "Public workflow input name",
            port=False,
        ),
    ),
    color="orange",
)


def _workflow_output(
    _inputs: Mapping[str, Any], _parameters: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Pass a value through to the public workflow output."""
    return {"value": _inputs["value"]}


WORKFLOW_OUTPUT = NodeDefinition(
    id="workflow-output",
    icon="mdi-export",
    label="Workflow Output",
    description="Defines a named public output for the workflow.",
    ports=(
        PortDefinition("value", PortDirection.INPUT, ANY, "Value"),
        PortDefinition("value", PortDirection.OUTPUT, ANY, "Value"),
    ),
    executor=_workflow_output,
    parameters=(
        ParameterDefinition(
            "name",
            ParameterKind.TEXT,
            "Output name",
            "output",
            "Public workflow output name",
            port=False,
        ),
    ),
    color="orange",
)


AVAILABLE_NODES = (WORKFLOW_INPUT, WORKFLOW_OUTPUT)

__all__ = ["AVAILABLE_NODES", "WORKFLOW_INPUT", "WORKFLOW_OUTPUT"]
