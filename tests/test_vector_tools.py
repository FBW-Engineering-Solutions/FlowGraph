"""Numeric correctness, demand-driven execution, and catalog integration."""

from contextlib import ExitStack
from unittest.mock import patch

import numpy as np
import pytest

from flowgraph.adapters import ADAPTERS
from flowgraph.adapters.simple_sources import SET_LIST_FLOAT
from flowgraph.adapters.vector_tools import VECTOR_STATISTICS
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import (
    ExecContext,
    NodeDefinition,
    PortDefinition,
    PortDirection,
    WorkflowEdge,
    WorkflowExecutor,
    WorkflowGraph,
)
from flowgraph.application.workflow_io import load_workflow, save_workflow
from flowgraph.application.workflow_web_catalog import workflow_web_catalog

OUTPUTS = ("min", "min_index", "max", "max_index", "mean", "std")


def statistics(vector, connected=OUTPUTS):
    return VECTOR_STATISTICS.executor(
        {"vector": vector}, {}, ExecContext(connected_output_ports=frozenset(connected))
    )


@pytest.mark.parametrize(
    "vector", [[3, -2, 7, -2, 7], np.array([3, -2, 7, -2, 7], dtype=np.float32)]
)
def test_statistics_values_indices_and_source_preservation(vector):
    original = np.array(vector, copy=True)
    result = statistics(vector)
    assert result == pytest.approx(
        {
            "min": -2.0,
            "min_index": 1,
            "max": 7.0,
            "max_index": 2,
            "mean": 2.6,
            "std": np.std(original),
        }
    )
    assert type(result["min_index"]) is int
    assert type(result["max_index"]) is int
    for name in ("min", "max", "mean", "std"):
        assert type(result[name]) is float
    np.testing.assert_array_equal(vector, original)


def test_single_value_and_constant_vectors():
    assert statistics([4]) == {
        "min": 4.0,
        "min_index": 0,
        "max": 4.0,
        "max_index": 0,
        "mean": 4.0,
        "std": 0.0,
    }
    assert statistics([4, 4, 4])["std"] == 0.0


@pytest.mark.parametrize("connected", [(), *[(name,) for name in OUTPUTS]])
def test_only_connected_statistics_are_computed(connected):
    operations = {
        "min": "min",
        "min_index": "argmin",
        "max": "max",
        "max_index": "argmax",
        "mean": "mean",
        "std": "std",
    }
    with ExitStack() as stack:
        mocks = {
            name: stack.enter_context(
                patch(
                    f"flowgraph.adapters.vector_tools.np.{operation}", wraps=getattr(np, operation)
                )
            )
            for name, operation in operations.items()
        }
        result = statistics([1, 2, 3], connected)
    for name, mock in mocks.items():
        assert mock.call_count == int(name in connected)
    for name in OUTPUTS:
        if name not in connected:
            if name.endswith("_index"):
                assert result[name] == -1
            else:
                assert np.isnan(result[name])


def test_extrema_share_index_search_when_value_and_index_are_connected():
    with (
        patch("flowgraph.adapters.vector_tools.np.min") as minimum,
        patch("flowgraph.adapters.vector_tools.np.max") as maximum,
    ):
        result = statistics([4, 1, 9], ("min", "min_index", "max", "max_index"))
    minimum.assert_not_called()
    maximum.assert_not_called()
    assert result["min"] == 1.0 and result["min_index"] == 1
    assert result["max"] == 9.0 and result["max_index"] == 2


def test_unused_node_does_not_even_convert_input():
    with patch("flowgraph.adapters.vector_tools.np.asarray") as convert:
        statistics(object(), ())
        VECTOR_STATISTICS.executor({}, {})
    convert.assert_not_called()


@pytest.mark.parametrize("vector", [[], 1, [[1, 2]], np.zeros((2, 2))])
def test_invalid_vector_shape(vector):
    with pytest.raises(ValueError, match="non-empty one-dimensional"):
        statistics(vector)


@pytest.mark.parametrize("vector", [["1", "2"], [True, False], [1j], [object()]])
def test_non_real_numeric_vectors_are_rejected(vector):
    with pytest.raises(TypeError, match="real integer or floating-point"):
        statistics(vector)


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_nonfinite_values_are_rejected(value):
    with pytest.raises(ValueError, match="finite"):
        statistics([1, value])


def test_registration_and_serialized_catalog():
    assert ADAPTERS.require("vector-statistics") is VECTOR_STATISTICS
    group = next(g for g in workflow_web_catalog()["groups"] if g["label"] == "Vector Tools")
    node = next(n for n in group["nodes"] if n["id"] == VECTOR_STATISTICS.id)
    assert node["requirements"] == ["py:numpy"]
    assert [(p["name"], p["data_type_id"]) for p in node["ports"]] == [
        ("vector", "any"),
        ("min", "float"),
        ("min_index", "integer"),
        ("max", "float"),
        ("max_index", "integer"),
        ("mean", "float"),
        ("std", "float"),
    ]


def test_connected_and_exported_outputs_round_trip_and_execute(tmp_path):
    registry = create_node_registry()
    sink = NodeDefinition(
        id="statistics-sink",
        label="Sink",
        icon="",
        ports=(
            PortDefinition(
                "value", PortDirection.INPUT, VECTOR_STATISTICS.output("mean").data_type
            ),
        ),
        executor=lambda _inputs, _parameters, _context: {},
    )
    registry.register(sink)
    graph = WorkflowGraph(
        [
            SET_LIST_FLOAT.create_instance("source", parameters={"value": [1.0, 3.0, 5.0]}),
            VECTOR_STATISTICS.create_instance("statistics"),
            sink.create_instance("sink"),
        ]
    )
    graph.add_edge(WorkflowEdge("source", "value", "statistics", "vector"), registry)
    graph.add_edge(WorkflowEdge("statistics", "mean", "sink", "value"), registry)
    graph.export_output("maximum_index", "statistics", "max_index", registry)
    path = tmp_path / "statistics.json"
    save_workflow(graph, path)
    result = WorkflowExecutor(registry).run(load_workflow(path, registry))
    outputs = result.node_outputs["statistics"]
    assert outputs["mean"] == 3.0
    assert outputs["max_index"] == 2
    assert result.node_inputs["sink"]["value"] == 3.0
    assert np.isnan(outputs["std"]) and np.isnan(outputs["min"])
    assert outputs["min_index"] == -1
