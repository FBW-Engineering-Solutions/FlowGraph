"""Rank-aware array contracts and checked, allocation-free edge conversions."""

import json

import numpy as np
import pytest

from flowgraph.adapters import AdapterGroup
from flowgraph.adapters.data_types import ANY, ARRAY, ARRAY_1D, ARRAY_2D, IMAGEJ, LIST_FLOAT
from flowgraph.application.port_conversions import resolve_port_conversion, resolve_value_conversion
from flowgraph.application.workflow_core import (
    NodeDefinition,
    NodeExecutionError,
    NodeRegistry,
    PortDefinition,
    PortDirection,
    WorkflowEdge,
    WorkflowExecutor,
    WorkflowGraph,
    WorkflowValidationError,
)
from flowgraph.application.workflow_io import load_workflow, save_workflow
from flowgraph.application.workflow_web_catalog import workflow_web_catalog


@pytest.mark.parametrize("data_type,rank", [(ARRAY, None), (ARRAY_1D, 1), (ARRAY_2D, 2)])
def test_array_types_validate_container_and_rank_only(data_type, rank):
    for shape in [(), (0,), (3,), (0, 1), (3, 1), (1, 3), (2, 3), (2, 3, 3)]:
        for dtype in [float, int, complex, bool, str, object]:
            value = np.empty(shape, dtype=dtype)
            assert data_type.accepts(value) == (rank is None or len(shape) == rank)
    for value in [None, 1.0, [], [1.0], [[1.0]], (1.0,)]:
        assert not data_type.accepts(value)
    assert ARRAY_1D.accepts(np.array([np.nan, np.inf]))


@pytest.mark.parametrize("source", [ARRAY, ARRAY_1D, ARRAY_2D])
@pytest.mark.parametrize("target", [ARRAY, ARRAY_1D, ARRAY_2D])
def test_array_direct_compatibility_is_rank_aware(source, target):
    assert source.is_compatible_with(target) == (source is target or target is ARRAY)
    assert source.is_compatible_with(ANY)
    assert ANY.is_compatible_with(target)


@pytest.mark.parametrize("array_type", [ARRAY, ARRAY_1D, ARRAY_2D])
@pytest.mark.parametrize("other_type", [LIST_FLOAT, IMAGEJ])
def test_array_types_do_not_reinterpret_list_or_image_types(array_type, other_type):
    assert not array_type.is_compatible_with(other_type)
    assert not other_type.is_compatible_with(array_type)
    bridged = array_type is ARRAY_1D and other_type is LIST_FLOAT
    assert (resolve_port_conversion(array_type, other_type) is not None) == bridged
    assert (resolve_port_conversion(other_type, array_type) is not None) == bridged
    assert LIST_FLOAT.accepts([1.0])
    assert not LIST_FLOAT.accepts(np.array([1.0]))


def _graph(source_type, target_type, value):
    source = NodeDefinition(
        id="array-source",
        label="Array source",
        icon="",
        ports=(PortDefinition("value", PortDirection.OUTPUT, source_type),),
        executor=lambda _inputs, _parameters: {"value": value},
    )
    sink = NodeDefinition(
        id="array-sink",
        label="Array sink",
        icon="",
        ports=(PortDefinition("value", PortDirection.INPUT, target_type),),
        executor=lambda _inputs, _parameters: {},
    )
    registry = NodeRegistry()
    registry.register(source)
    registry.register(sink)
    graph = WorkflowGraph([source.create_instance("source"), sink.create_instance("sink")])
    graph.add_edge(WorkflowEdge("source", "value", "sink", "value"), registry)
    return graph, registry, source, sink


@pytest.mark.parametrize(
    "source,target,shape,expected_shape,converted",
    [
        (ARRAY, ARRAY, (2, 3, 3), (2, 3, 3), False),
        (ARRAY_1D, ARRAY_1D, (3,), (3,), False),
        (ARRAY_2D, ARRAY_2D, (3, 2), (3, 2), False),
        (ARRAY_1D, ARRAY, (3,), (3,), False),
        (ARRAY_2D, ARRAY, (3, 2), (3, 2), False),
        (ARRAY, ARRAY_1D, (3,), (3,), True),
        (ARRAY, ARRAY_1D, (3, 1), (3,), True),
        (ARRAY, ARRAY_2D, (3, 2), (3, 2), True),
        (ARRAY_2D, ARRAY_1D, (3, 1), (3,), True),
        (ARRAY_2D, ARRAY_1D, (0, 1), (0,), True),
    ],
)
def test_array_edges_round_trip_and_preserve_storage(
    tmp_path, source, target, shape, expected_shape, converted
):
    value = np.arange(np.prod(shape), dtype=np.int32).reshape(shape)
    original = value.copy()
    graph, registry, _, _ = _graph(source, target, value)
    path = tmp_path / "arrays.json"
    save_workflow(graph, path)
    restored = load_workflow(path, registry)
    assert (restored.edge_conversion(restored.edges[0], registry) is not None) == converted
    result = WorkflowExecutor(registry).run(restored)
    actual = result.node_inputs["sink"]["value"]
    assert actual.shape == expected_shape
    assert actual.dtype == value.dtype
    if value.size:
        assert np.shares_memory(actual, value)
    if shape == expected_shape:
        assert actual is value
    np.testing.assert_array_equal(value, original)
    assert result.node_outputs["source"]["value"] is value


@pytest.mark.parametrize(
    "source,target,shape",
    [
        (ARRAY, ARRAY_1D, ()),
        (ARRAY, ARRAY_1D, (1, 3)),
        (ARRAY, ARRAY_1D, (3, 2)),
        (ARRAY, ARRAY_1D, (2, 3, 3)),
        (ARRAY, ARRAY_2D, (3,)),
        (ARRAY, ARRAY_2D, (2, 3, 3)),
        (ARRAY_2D, ARRAY_1D, (3, 2)),
    ],
)
def test_array_connections_allow_checked_runtime_failure(source, target, shape):
    graph, registry, _, _ = _graph(source, target, np.empty(shape))
    assert graph.validate(registry) == ()
    with pytest.raises(NodeExecutionError, match="received shape") as caught:
        WorkflowExecutor(registry).run(graph)
    assert caught.value.node_id == "sink"


@pytest.mark.parametrize("source,shape", [(ARRAY_1D, (3, 1)), (ARRAY_2D, (3,))])
def test_array_outputs_must_satisfy_declared_rank(source, shape):
    graph, registry, _, _ = _graph(source, ARRAY, np.empty(shape))
    with pytest.raises(NodeExecutionError, match="expected") as caught:
        WorkflowExecutor(registry).run(graph)
    assert caught.value.node_id == "source"


def test_array_column_conversion_handles_strided_readonly_views():
    value = np.arange(24).reshape(12, 2)[::2, :1]
    value.setflags(write=False)
    conversion = resolve_value_conversion(value, ARRAY_1D)
    actual = conversion.convert(value)
    assert np.shares_memory(actual, value)
    assert not actual.flags.writeable
    np.testing.assert_array_equal(actual, value[:, 0])
    assert resolve_value_conversion(actual, ARRAY_1D) is None
    assert resolve_value_conversion([1.0], ARRAY_1D) is not None


def test_1d_to_2d_does_not_implicitly_choose_a_shape():
    with pytest.raises(WorkflowValidationError):
        _graph(ARRAY_1D, ARRAY_2D, np.arange(3))


def test_array_metadata_and_rules_export_for_custom_nodes():
    _, _, source, sink = _graph(ARRAY, ARRAY_1D, np.arange(3))
    group = AdapterGroup(label="Array tests", node_definitions=(source, sink))
    catalog = workflow_web_catalog(extra_groups=(group,))
    nodes = catalog["groups"][-1]["nodes"]
    assert nodes[0]["ports"][0]["data_type_id"] == "array"
    assert nodes[1]["ports"][0]["data_type_label"] == "1D Array"
    pairs = {(rule["source_type_id"], rule["target_type_id"]) for rule in catalog["conversions"]}
    assert {
        ("array-1d", "array"),
        ("array-2d", "array"),
        ("array", "array-1d"),
        ("array", "array-2d"),
        ("array-2d", "array-1d"),
    } <= pairs
    json.dumps(catalog)
