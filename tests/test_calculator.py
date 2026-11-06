"""Calculator expressions, input ownership, alias resolution and graph integration."""

import numpy as np
import pytest

from flowgraph.adapters import ADAPTERS
from flowgraph.adapters.calculator import CALCULATOR
from flowgraph.adapters.data_types import ANY
from flowgraph.adapters.simple_sources import SET_FLOAT, SET_STRING
from flowgraph.adapters.vector_tools import EXTRACT_VECTOR_VALUE
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import (
    NodeDefinition,
    NodeExecutionError,
    PortDefinition,
    PortDirection,
    WorkflowEdge,
    WorkflowExecutor,
    WorkflowGraph,
    WorkflowValidationError,
)
from flowgraph.application.workflow_io import load_workflow, save_workflow
from flowgraph.application.workflow_session import WorkflowSession
from flowgraph.application.workflow_web_catalog import workflow_web_catalog


def calculate(formula, **inputs):
    return CALCULATOR.executor(inputs, {"formula": formula})["result"]


@pytest.mark.parametrize(
    "formula, inputs, expected",
    [
        ("2 + 3 * 4", {}, 14),
        ("input_1 * 2 + input_2", {"input_1": 3, "input_2": 0.5}, 6.5),
        ("np.mean(input_1)", {"input_1": [1, 2, 3]}, 2.0),
        ("input_1 * 2", {"input_1": [1, 2, 3]}, [2, 4, 6]),
        ("np.sin(input_1)", {"input_1": np.array([0.0])}, [0.0]),
        ("input_10 - input_2", {"input_10": 10, "input_2": 2}, 8),
        ("np.stack([input_1, input_2])", {"input_1": [1, 2], "input_2": [3, 4]}, [[1, 2], [3, 4]]),
        ("np.array([input_1 * i for i in range(3)])", {"input_1": 2}, [0, 2, 4]),
        ("input_1 > 1", {"input_1": [1, 2]}, [False, True]),
        ("input_1 + 1j", {"input_1": 2}, 2 + 1j),
    ],
)
def test_expressions(formula, inputs, expected):
    result = calculate(formula, **inputs)
    np.testing.assert_array_equal(result, expected)
    if isinstance(result, np.ndarray):
        assert not result.flags.writeable


def test_default_and_connected_formula():
    assert CALCULATOR.executor({}, {}) == {"result": 0}
    assert CALCULATOR.executor({"formula": "3 + 4"}, {"formula": "0"}) == {"result": 7}


def test_zero_copy_views_and_input_flags():
    source = np.arange(12).reshape(3, 4)
    result = calculate("input_1[:, ::2]", input_1=source)
    assert np.shares_memory(source, result)
    assert source.flags.writeable
    assert not result.flags.writeable
    np.testing.assert_array_equal(source, np.arange(12).reshape(3, 4))
    with pytest.raises(ValueError, match="read-only"):
        result[0, 0] = -1
    with pytest.raises(ValueError, match="read-only"):
        calculate("np.add(input_1, 1, out=input_1)", input_1=source)
    assert source.flags.writeable


@pytest.mark.parametrize("array", [np.array(3), np.empty((0, 2)), np.array([np.nan, np.inf])])
def test_array_shape_dtype_nonfinite_preserved(array):
    result = calculate("input_1", input_1=array)
    assert result.shape == array.shape
    assert result.dtype == array.dtype
    assert np.shares_memory(array, result) or not array.size
    assert not result.flags.writeable
    np.testing.assert_array_equal(result, array)


@pytest.mark.parametrize("value", ["text", {}, None, np.array(["text"]), [object()]])
def test_invalid_inputs(value):
    with pytest.raises(TypeError, match="Calculator input"):
        calculate("input_1", input_1=value)


@pytest.mark.parametrize("formula", ["'text'", "{}", "None", "[1, 2]", "np.array(['text'])"])
def test_invalid_results(formula):
    with pytest.raises(TypeError, match="Calculator result"):
        calculate(formula)


@pytest.mark.parametrize("formula", ["", "  ", None, 4])
def test_invalid_formula_values(formula):
    with pytest.raises(ValueError, match="non-empty Python expression"):
        calculate(formula)


@pytest.mark.parametrize(
    "formula, message",
    [
        ("input_1 +", "SyntaxError"),
        ("missing", "NameError"),
        ("1 / 0", "ZeroDivisionError"),
        ("x = 1", "SyntaxError"),
        ("np.ones(2) + np.ones(3)", "ValueError"),
    ],
)
def test_formula_errors(formula, message):
    with pytest.raises(ValueError, match=message):
        calculate(formula)


def alias_graph(names, formula):
    registry = create_node_registry()
    nodes = [CALCULATOR.create_instance("calc", parameters={"formula": formula})]
    for index, name in enumerate(names, 1):
        definition = NodeDefinition(
            f"source-{index}",
            "",
            "Source",
            (PortDefinition(name, PortDirection.OUTPUT, ANY),),
            lambda _i, _p, _ctx, value=index, port=name: {port: value},
        )
        registry.register(definition)
        nodes.append(definition.create_instance(f"source-{index}"))
    graph = WorkflowGraph(nodes)
    for index in range(1, len(names) + 1):
        graph.add_edge(
            WorkflowEdge(f"source-{index}", names[index - 1], "calc", f"input_{index}"), registry
        )
    return graph, registry


def test_aliases_and_numbered_names_together():
    graph, registry = alias_graph(["temperature", "pressure"], "temperature + input_2 + pressure")
    assert WorkflowExecutor(registry).run(graph).node_outputs["calc"]["result"] == 5


@pytest.mark.parametrize(
    "name",
    ["value", "input_1", "input_125", "input_999", "np", "__builtins__", "sum", "bad-name", "for"],
)
def test_ambiguous_invalid_reserved_aliases_omitted(name):
    names = [name, name] if name == "value" else [name]
    formula = f"int({name!r} in locals()) + input_1"
    graph, registry = alias_graph(names, formula)
    result = WorkflowExecutor(registry).run(graph).node_outputs["calc"]["result"]
    # Numbered inputs, NumPy and builtins still exist, but never point at the alias value.
    expected = 2 if name in {"input_1", "np", "__builtins__"} else 1
    assert result == expected


def test_duplicate_alias_disappears_and_returns_after_disconnect():
    graph, registry = alias_graph(["value", "value"], "input_1 + input_2")
    assert WorkflowExecutor(registry).run(graph).node_outputs["calc"]["result"] == 3
    graph.require_node("calc").parameters["formula"] = "value"
    with pytest.raises(NodeExecutionError, match="NameError"):
        WorkflowExecutor(registry).run(graph)
    graph.remove_edge(graph.edges[1], registry)
    assert WorkflowExecutor(registry).run(graph).node_outputs["calc"]["result"] == 1


def test_formula_connection_persistence_capacity_and_downstream(tmp_path):
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            SET_FLOAT.create_instance("source", parameters={"value": 3.5}),
            SET_STRING.create_instance("formula", parameters={"value": "value * 2"}),
            CALCULATOR.create_instance("calc", parameters={"formula": "0"}),
            SET_FLOAT.create_instance("sink"),
        ]
    )
    graph.add_edge(WorkflowEdge("source", "value", "calc", "input_1"), registry)
    graph.add_edge(WorkflowEdge("formula", "value", "calc", "formula"), registry)
    graph.add_edge(WorkflowEdge("calc", "result", "sink", "value"), registry)
    path = tmp_path / "calculator.json"
    save_workflow(graph, path)
    loaded = load_workflow(path, registry)
    result = WorkflowExecutor(registry).run(loaded)
    assert result.node_outputs["sink"]["value"] == 7.0
    assert loaded.require_node("calc").parameters["formula"] == "value * 2"
    for index in range(2, 126):
        loaded.add_edge(WorkflowEdge("source", "value", "calc", f"input_{index}"), registry)
    with pytest.raises(WorkflowValidationError, match="input_126"):
        loaded.add_edge(WorkflowEdge("source", "value", "calc", "input_126"), registry)
    loaded.require_node("calc").parameters["formula"] = "input_125"
    loaded.remove_edge(next(e for e in loaded.edges if e.target_port == "formula"), registry)
    assert WorkflowExecutor(registry).run(loaded).node_outputs["calc"]["result"] == 3.5


def test_exported_inputs_and_outputs():
    registry = create_node_registry()
    graph = WorkflowGraph([CALCULATOR.create_instance("calc")])
    graph.export_input("data", "calc", "input_1", registry)
    graph.export_input("formula", "calc", "formula", registry)
    graph.export_output("result", "calc", "result", registry)
    result = graph.execute({"data": [1, 2], "formula": "input_1 * 3"}, registry)
    np.testing.assert_array_equal(result["result"], [3, 6])


def test_array_result_connects_to_typed_array_consumer():
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            CALCULATOR.create_instance("calc", parameters={"formula": "np.arange(4) * 2"}),
            EXTRACT_VECTOR_VALUE.create_instance("extract", parameters={"index": -1}),
        ]
    )
    graph.add_edge(WorkflowEdge("calc", "result", "extract", "vector"), registry)
    result = WorkflowExecutor(registry).run(graph)
    assert result.node_outputs["extract"]["value"] == 6.0


def test_reserved_aliases_do_not_replace_numpy_or_numbered_values():
    graph, registry = alias_graph(["input_2", "np"], "input_1 + input_2 + np.mean([2, 4])")
    assert WorkflowExecutor(registry).run(graph).node_outputs["calc"]["result"] == 6.0


def test_catalog_registration_and_cache_policy():
    assert ADAPTERS.require("calculator") is CALCULATOR
    group = next(g for g in workflow_web_catalog()["groups"] if g["label"] == "Vector Tools")
    node = next(n for n in group["nodes"] if n["id"] == "calculator")
    assert node["requirements"] == ["py:numpy"]
    assert node["cache_policy"] == "always"
    assert node["ports"][0]["expandable"] == 125
    assert node["parameters"][0]["port"] is True
    assert node["parameters"][0]["name"] == "formula"
    assert node["ports"][-1]["is_param"] is True


def test_session_reexecutes_expression(monkeypatch):
    calls = []
    monkeypatch.setattr(np.random, "random", lambda: calls.append(1) or float(len(calls)))
    graph = WorkflowGraph(
        [CALCULATOR.create_instance("calc", parameters={"formula": "np.random.random()"})]
    )
    session = WorkflowSession(create_node_registry())
    session.run(graph)
    session.run(graph)
    assert len(calls) == 2
