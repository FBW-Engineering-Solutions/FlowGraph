"""Tests for the optional CoSApp workflow adapter."""

from __future__ import annotations

import pytest

from flowgraph.adapters.cosapp import COSAPP_WORKFLOW
from flowgraph.adapters.simple_sources import SET_FLOAT
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import WorkflowEdge, WorkflowExecutor, WorkflowGraph


def _model_file(tmp_path) -> str:
    """Write a compact external CoSApp model used by integration tests."""
    model = tmp_path / "scale_model.py"
    model.write_text(
        """from cosapp.base import System


class Scale(System):
    def setup(self):
        self.add_inward('value', 1.0)
        self.add_outward('doubled', 0.0)

    def compute(self):
        self.doubled = self.value * 2


def create_model():
    root = System('model')
    root.add_child(Scale('scale'))
    return root
""",
        encoding="utf-8",
    )
    return str(model)


def test_cosapp_workflow_exposes_declared_ports_and_runs_external_model(tmp_path) -> None:
    registry = create_node_registry()
    model_file = _model_file(tmp_path)
    node = COSAPP_WORKFLOW.create_instance(
        "cosapp",
        parameters={
            "model_file": model_file,
            "inputs": '{"input_value": "scale.value"}',
            "outputs": '{"doubled": "scale.doubled"}',
        },
    )
    source = SET_FLOAT.create_instance("source", parameters={"value": 4.5})
    graph = WorkflowGraph([source, node])
    graph.add_edge(WorkflowEdge("source", "value", "cosapp", "input_value"), registry)

    result = WorkflowExecutor(registry).run(graph)

    assert [
        (port.name, port.direction.value) for port in COSAPP_WORKFLOW.ports_for(node.parameters)
    ] == [
        ("input_value", "input"),
        ("result", "output"),
        ("doubled", "output"),
    ]
    assert result.node_outputs["cosapp"]["doubled"] == 9.0
    assert result.node_outputs["cosapp"]["result"].scale.doubled == 9.0


def test_cosapp_workflow_rejects_invalid_export_configuration() -> None:
    with pytest.raises(ValueError, match="reserved output name"):
        COSAPP_WORKFLOW.ports_for({"inputs": "{}", "outputs": '{"result": "scale.doubled"}'})

    with pytest.raises(ValueError, match="must be valid JSON"):
        COSAPP_WORKFLOW.ports_for({"inputs": "not JSON", "outputs": "{}"})


def test_cosapp_workflow_reports_missing_declared_path(tmp_path) -> None:
    with pytest.raises(ValueError, match="input path 'scale.missing' does not exist"):
        COSAPP_WORKFLOW.executor(
            {"value": 3.0},
            {
                "model_file": _model_file(tmp_path),
                "factory": "create_model",
                "inputs": '{"value": "scale.missing"}',
                "outputs": "{}",
            },
        )
