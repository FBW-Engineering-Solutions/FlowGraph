"""Indexed vector extraction, shared storage, and workflow integration."""

from unittest.mock import patch

import numpy as np
import pytest

from flowgraph.adapters import ADAPTERS
from flowgraph.adapters.simple_sources import SET_ARRAY_1D, SET_INT
from flowgraph.adapters.vector_tools import EXTRACT_VECTOR_VALUE
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import WorkflowEdge, WorkflowExecutor, WorkflowGraph
from flowgraph.application.workflow_io import load_workflow, save_workflow
from flowgraph.application.workflow_web_catalog import workflow_web_catalog


@pytest.mark.parametrize("index, expected", [(0, 10.0), (1, 20.0), (-1, 30.0), (-3, 10.0)])
@pytest.mark.parametrize("dtype", [np.int64, np.float32, np.float64])
def test_extract_value_without_copy_or_mutation(index, expected, dtype):
    vector = np.array([10, 99, 20, 99, 30], dtype=dtype)[::2]
    original = vector.copy()
    asarray = np.asarray

    def check_shared_storage(value):
        converted = asarray(value)
        assert converted is vector
        return converted

    with patch("flowgraph.adapters.vector_tools.np.asarray", side_effect=check_shared_storage):
        result = EXTRACT_VECTOR_VALUE.executor({"vector": vector}, {"index": index})
    assert result == {"value": expected}
    assert type(result["value"]) is float
    np.testing.assert_array_equal(vector, original)
    assert vector.flags.writeable


def test_default_index_and_readonly_array():
    vector = np.array([4.0, 5.0])
    vector.flags.writeable = False
    assert EXTRACT_VECTOR_VALUE.executor({"vector": vector}, {}) == {"value": 4.0}
    assert not vector.flags.writeable


def test_connected_index_overrides_parameter():
    assert EXTRACT_VECTOR_VALUE.executor(
        {"vector": [10, 20], "index": np.int64(1)}, {"index": 0}
    ) == {"value": 20.0}


@pytest.mark.parametrize("index", [2, -3, 10**100])
def test_invalid_bounds(index):
    with pytest.raises(IndexError, match="out of range for vector length 2"):
        EXTRACT_VECTOR_VALUE.executor({"vector": [1, 2]}, {"index": index})


@pytest.mark.parametrize("index", [True, np.bool_(False), 1.0, "1", None])
def test_invalid_index_type(index):
    with pytest.raises(TypeError, match="index must be an integer"):
        EXTRACT_VECTOR_VALUE.executor({"vector": [1, 2]}, {"index": index})


@pytest.mark.parametrize("vector", [[], 1, [[1], [2]], [[1, 2]], np.zeros((2, 2))])
def test_invalid_shape(vector):
    with pytest.raises(ValueError, match="non-empty one-dimensional"):
        EXTRACT_VECTOR_VALUE.executor({"vector": vector}, {})


@pytest.mark.parametrize("vector", [[True], ["1"], [1j], [object()]])
def test_invalid_vector_type(vector):
    with pytest.raises(TypeError, match="real integer or floating-point"):
        EXTRACT_VECTOR_VALUE.executor({"vector": vector}, {})


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_nonfinite_selected_value_is_preserved(value):
    result = EXTRACT_VECTOR_VALUE.executor({"vector": [value]}, {})["value"]
    assert np.isnan(result) if np.isnan(value) else result == value


def test_registration_and_catalog():
    assert ADAPTERS.require("extract-vector-value") is EXTRACT_VECTOR_VALUE
    group = next(g for g in workflow_web_catalog()["groups"] if g["label"] == "Vector Tools")
    node = next(n for n in group["nodes"] if n["id"] == EXTRACT_VECTOR_VALUE.id)
    assert node["requirements"] == ["py:numpy"]
    assert [(p["name"], p["data_type_id"]) for p in node["ports"]] == [
        ("vector", "array-1d"),
        ("value", "float"),
        ("index", "integer"),
    ]


@pytest.mark.parametrize("connected_index", [False, True])
def test_workflow_roundtrip_and_execution(tmp_path, connected_index):
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            SET_ARRAY_1D.create_instance("source", parameters={"value": [10, 20, 30]}),
            SET_INT.create_instance("index", parameters={"value": -1}),
            EXTRACT_VECTOR_VALUE.create_instance("extract", parameters={"index": 1}),
        ]
    )
    graph.add_edge(WorkflowEdge("source", "value", "extract", "vector"), registry)
    if connected_index:
        graph.add_edge(WorkflowEdge("index", "value", "extract", "index"), registry)
    graph.export_output("selected", "extract", "value", registry)
    path = tmp_path / "extract.json"
    save_workflow(graph, path)
    result = WorkflowExecutor(registry).run(load_workflow(path, registry))
    assert result.node_outputs["extract"] == {"value": 30.0 if connected_index else 20.0}
