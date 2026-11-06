"""Expandable scalar aggregation, ordering, persistence, and capacity."""

import numpy as np
import pytest

from flowgraph.adapters import ADAPTERS
from flowgraph.adapters.simple_sources import SET_FLOAT, SET_INT
from flowgraph.adapters.vector_tools import SCALARS_TO_ARRAY_1D
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import (
    WorkflowEdge,
    WorkflowExecutor,
    WorkflowGraph,
    WorkflowValidationError,
)
from flowgraph.application.workflow_io import load_workflow, save_workflow
from flowgraph.application.workflow_web_catalog import workflow_web_catalog


def test_numeric_order_and_gaps():
    inputs = {"scalar_125": 125.0, "scalar_10": 10, "scalar_2": np.float32(2)}
    array = SCALARS_TO_ARRAY_1D.executor(inputs, {})["array"]
    np.testing.assert_array_equal(array, [2.0, 10.0, 125.0])
    assert array.shape == (3,)
    assert array.dtype == np.float64
    assert not array.flags.writeable
    with pytest.raises(ValueError, match="read-only"):
        array[0] = 4
    assert inputs == {"scalar_125": 125.0, "scalar_10": 10, "scalar_2": np.float32(2)}


def test_no_connections_returns_empty_readonly_array():
    graph = WorkflowGraph([SCALARS_TO_ARRAY_1D.create_instance("collect")])
    array = WorkflowExecutor(create_node_registry()).run(graph).node_outputs["collect"]["array"]
    assert array.shape == (0,)
    assert array.dtype == np.float64
    assert not array.flags.writeable


@pytest.mark.parametrize("value", [True, np.bool_(False), "1", [1], np.array([1]), 1j, None])
def test_non_scalar_values_are_rejected(value):
    with pytest.raises(TypeError, match="must be a real scalar"):
        SCALARS_TO_ARRAY_1D.executor({"scalar_1": value}, {})


def test_nonfinite_values_are_preserved():
    array = SCALARS_TO_ARRAY_1D.executor(
        {"scalar_1": np.nan, "scalar_2": np.inf, "scalar_3": -np.inf}, {}
    )["array"]
    np.testing.assert_array_equal(array, [np.nan, np.inf, -np.inf])


def test_catalog_and_registration():
    assert ADAPTERS.require("scalars-to-array-1d") is SCALARS_TO_ARRAY_1D
    group = next(g for g in workflow_web_catalog()["groups"] if g["label"] == "Vector Tools")
    node = next(n for n in group["nodes"] if n["id"] == SCALARS_TO_ARRAY_1D.id)
    scalar, array = node["ports"]
    assert (scalar["name"], scalar["data_type_id"], scalar["expandable"]) == (
        "scalar",
        "float",
        125,
    )
    assert scalar["required"] is False
    assert (array["name"], array["data_type_id"]) == ("array", "array-1d")


def test_expansion_capacity_roundtrip_and_disconnection(tmp_path):
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            SET_INT.create_instance("integer", parameters={"value": 7}),
            SET_FLOAT.create_instance("float", parameters={"value": 2.5}),
            SCALARS_TO_ARRAY_1D.create_instance("collect"),
        ]
    )
    node = graph.require_node("collect")

    def input_names():
        return [
            p.name
            for p in SCALARS_TO_ARRAY_1D.ports_for_instance(node)
            if p.name.startswith("scalar_")
        ]

    assert input_names() == ["scalar_1"]
    for index in range(1, 126):
        source = "integer" if index % 2 else "float"
        graph.add_edge(WorkflowEdge(source, "value", "collect", f"scalar_{index}"), registry)
        assert len(input_names()) == min(index + 1, 125)
    with pytest.raises(WorkflowValidationError, match="scalar_126"):
        graph.add_edge(WorkflowEdge("integer", "value", "collect", "scalar_126"), registry)

    path = tmp_path / "scalars.json"
    save_workflow(graph, path)
    loaded = load_workflow(path, registry)
    array = WorkflowExecutor(registry).run(loaded).node_outputs["collect"]["array"]
    np.testing.assert_array_equal(array, [7.0 if i % 2 else 2.5 for i in range(1, 126)])
    assert not array.flags.writeable

    edge = next(e for e in loaded.edges if e.target_port == "scalar_2")
    loaded.remove_edge(edge, registry)
    array = WorkflowExecutor(registry).run(loaded).node_outputs["collect"]["array"]
    assert len(array) == 124
    np.testing.assert_array_equal(array[:3], [7.0, 7.0, 2.5])
