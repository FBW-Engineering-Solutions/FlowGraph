"""Array nodes, scalar field connections, and Python-list interoperability."""

import numpy as np
import pytest
from Muscat.MeshContainers.Mesh import Mesh

from flowgraph.adapters.data_types import (
    ARRAY_1D,
    FLOAT,
    LIST_ANY,
    LIST_FLOAT,
    LIST_INT,
    MESH_DOCUMENT,
    VEC3D,
)
from flowgraph.adapters.field_ops import EXTRACT_FIELD_NODE
from flowgraph.adapters.simple_sources import SET_ARRAY_1D
from flowgraph.adapters.table_tools import AGGREGATE_LISTS_TO_TABLE
from flowgraph.adapters.user_code import USER_FUNCTION
from flowgraph.adapters.vector_tools import VECTOR_STATISTICS
from flowgraph.adapters.workflow import BATCH_WORKFLOW
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.port_conversions import resolve_port_conversion
from flowgraph.application.workflow_core import (
    ExecContext,
    NodeDefinition,
    NodeExecutionError,
    PortDefinition,
    PortDirection,
    WorkflowEdge,
    WorkflowExecutor,
    WorkflowGraph,
)
from flowgraph.application.workflow_io import load_workflow, save_workflow
from flowgraph.domain.mesh_document import MeshDocument


def field_graph(values, consumer="zone-wrapped"):
    registry = create_node_registry()
    document = MeshDocument(Mesh())
    document.mesh.nodeFields["data"] = values
    source = NodeDefinition(
        id="field-source",
        label="Field source",
        icon="",
        ports=(PortDefinition("mesh", PortDirection.OUTPUT, MESH_DOCUMENT),),
        executor=lambda _inputs, _parameters: {"mesh": document},
    )
    registry.register(source)
    graph = WorkflowGraph(
        [
            source.create_instance("source"),
            EXTRACT_FIELD_NODE.create_instance("extract", parameters={"fieldName": "data"}),
            registry.create_instance(consumer, "consumer"),
        ]
    )
    graph.add_edge(WorkflowEdge("source", "mesh", "extract", "mesh"), registry)
    target_port = "field" if consumer == "zone-wrapped" else "vector"
    graph.add_edge(WorkflowEdge("extract", "field", "consumer", target_port), registry)
    return graph, registry


@pytest.mark.parametrize("column", [False, True])
@pytest.mark.parametrize("consumer", ["zone-wrapped", "vector-statistics"])
def test_extracted_scalar_fields_connect_and_round_trip(tmp_path, column, consumer):
    values = np.array([-2.0, 0.0, 3.0])
    if column:
        values = values[:, None]
    graph, registry = field_graph(values, consumer)
    if consumer == "vector-statistics":
        graph.export_output("mean", "consumer", "mean", registry)
    path = tmp_path / "field.json"
    save_workflow(graph, path)
    restored = load_workflow(path, registry)
    result = WorkflowExecutor(registry).run(restored)
    extracted = result.node_outputs["extract"]["field"]
    port = "field" if consumer == "zone-wrapped" else "vector"
    actual = result.node_inputs["consumer"][port]
    assert actual.shape == (3,)
    assert np.shares_memory(actual, extracted)
    if consumer == "zone-wrapped":
        zone = result.node_outputs["consumer"]["zone"]
        np.testing.assert_array_equal(zone(np.zeros((3, 3))), values.reshape(-1))
        assert np.shares_memory(zone.field, extracted)
        assert not zone.field.flags.writeable
        assert extracted.flags.writeable  # no mutation of the producer's flags
    else:
        assert result.node_outputs["consumer"]["mean"] == pytest.approx(1 / 3)
    # Execution must not persist large connected arrays into the editable default.
    assert restored.require_node("consumer").parameters.get("field", [0.0]) == [0.0]
    save_workflow(restored, path)


@pytest.mark.parametrize("consumer", ["zone-wrapped", "vector-statistics"])
@pytest.mark.parametrize("shape", [(3, 2), (3, 3, 3)])
def test_multicomponent_field_connection_is_allowed_but_fails_at_runtime(consumer, shape):
    graph, registry = field_graph(np.ones(shape), consumer)
    assert graph.validate(registry) == ()
    with pytest.raises(NodeExecutionError, match="received shape") as caught:
        WorkflowExecutor(registry).run(graph)
    assert caught.value.node_id == "consumer"


@pytest.mark.parametrize("values", [["1", "2"], [1j, 2j], [True, False], [np.nan], [np.inf]])
def test_wrapped_field_rejects_invalid_signed_distances(values):
    definition = create_node_registry().require("zone-wrapped")
    with pytest.raises((TypeError, ValueError), match="real integer|finite"):
        definition.executor({"field": np.asarray(values)}, {})


def test_wrapped_field_keeps_list_default_and_direct_column_support():
    definition = create_node_registry().require("zone-wrapped")
    assert definition.input("field").data_type is ARRAY_1D
    assert definition.parameters[0].kind is LIST_FLOAT
    assert definition.executor({}, {})["zone"].field.shape == (1,)
    values = np.array([[-1], [1]], dtype=np.int32)
    actual = definition.executor({"field": values}, {})["zone"].field
    assert actual.shape == (2,)
    assert actual.dtype == values.dtype
    assert np.shares_memory(actual, values)


def test_array_source_outputs_readonly_array_and_serializes_parameters(tmp_path):
    registry = create_node_registry()
    assert registry.require("set-array-1d") is SET_ARRAY_1D
    assert registry.get("set-list[float]") is None
    graph = WorkflowGraph([SET_ARRAY_1D.create_instance("source", parameters={"value": [1, 2.5]})])
    path = tmp_path / "array-source.json"
    save_workflow(graph, path)
    result = WorkflowExecutor(registry).run(load_workflow(path, registry))
    value = result.node_outputs["source"]["value"]
    assert ARRAY_1D.accepts(value)
    np.testing.assert_array_equal(value, [1.0, 2.5])
    assert not value.flags.writeable
    assert SET_ARRAY_1D.id == "set-array-1d"
    assert graph.require_node("source").parameters["value"] == [1, 2.5]


@pytest.mark.parametrize(
    "source_type,target_type,value,expected",
    [
        (LIST_FLOAT, ARRAY_1D, [1.0, 2.0], [1.0, 2.0]),
        (LIST_INT, ARRAY_1D, [1, 2], [1, 2]),
        (FLOAT, ARRAY_1D, 1.5, [1.5]),
        (VEC3D, ARRAY_1D, [1.0, 2.0, 3.0], [1.0, 2.0, 3.0]),
        (ARRAY_1D, LIST_FLOAT, np.array([1, 2]), [1.0, 2.0]),
        (ARRAY_1D, LIST_ANY, np.array(["a", "b"]), ["a", "b"]),
    ],
)
def test_sequence_array_conversions(source_type, target_type, value, expected):
    actual = resolve_port_conversion(source_type, target_type).convert(value)
    assert target_type.accepts(actual)
    np.testing.assert_array_equal(actual, expected)
    if target_type is ARRAY_1D:
        assert not actual.flags.writeable


def test_array_source_still_connects_to_list_table_and_parameter_ports(tmp_path):
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            SET_ARRAY_1D.create_instance("source", parameters={"value": [1.0, 2.0]}),
            SET_ARRAY_1D.create_instance("relay"),
            AGGREGATE_LISTS_TO_TABLE.create_instance("table"),
        ]
    )
    graph.add_edge(WorkflowEdge("source", "value", "relay", "value"), registry)
    graph.add_edge(WorkflowEdge("relay", "value", "table", "column_1"), registry)
    result = WorkflowExecutor(registry).run(graph)
    assert result.node_outputs["table"]["table"] == {"value": [1.0, 2.0]}
    assert graph.require_node("relay").parameters["value"] == [1.0, 2.0]
    save_workflow(graph, tmp_path / "relay.json")


def test_vector_statistics_supports_column_arrays_directly():
    result = VECTOR_STATISTICS.executor(
        {"vector": np.array([[1], [3]])}, {}, ExecContext(connected_output_ports={"mean"})
    )
    assert result["mean"] == 2.0


def test_array_source_reaches_user_function_as_a_real_float_list():
    registry = create_node_registry()
    user = USER_FUNCTION.create_instance(
        "user",
        parameters={
            "code": "def Execute(values: list[float]) -> tuple[list[float]]:\n"
            "    assert isinstance(values, list)\n"
            "    return (values + [3.0],)\n"
        },
    )
    graph = WorkflowGraph(
        [SET_ARRAY_1D.create_instance("source", parameters={"value": [1.0, 2.0]}), user]
    )
    graph.add_edge(WorkflowEdge("source", "value", "user", "values"), registry)
    result = WorkflowExecutor(registry).run(graph)
    assert result.node_outputs["user"]["output1"] == [1.0, 2.0, 3.0]


def test_array_source_preserves_float_batch_semantics(tmp_path):
    registry = create_node_registry()
    child_node = NodeDefinition(
        id="float-child",
        label="Float child",
        icon="",
        ports=(
            PortDefinition("value", PortDirection.INPUT, FLOAT),
            PortDefinition("value", PortDirection.OUTPUT, FLOAT),
        ),
        executor=lambda inputs, _parameters: {"value": inputs["value"] * 2},
    )
    registry.register(child_node)
    child = WorkflowGraph([child_node.create_instance("child")])
    child.export_input("value", "child", "value", registry)
    child.export_output("value", "child", "value", registry)
    batch = BATCH_WORKFLOW.create_instance("batch")
    batch.subworkflow = child
    graph = WorkflowGraph(
        [SET_ARRAY_1D.create_instance("source", parameters={"value": [1.0, 2.0]}), batch]
    )
    graph.add_edge(WorkflowEdge("source", "value", "batch", "value"), registry)
    path = tmp_path / "batch.json"
    save_workflow(graph, path)
    result = WorkflowExecutor(registry).run(load_workflow(path, registry))
    assert result.node_outputs["batch"]["value"] == [2.0, 4.0]
    assert ARRAY_1D.accepts(result.node_inputs["batch"]["value"])
