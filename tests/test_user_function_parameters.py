"""Scalar defaults, saved values and connected User Function parameters."""

import pytest

from flowgraph.adapters.simple_sources import SET_FLOAT
from flowgraph.adapters.user_code import USER_FUNCTION
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import WorkflowEdge, WorkflowExecutor, WorkflowGraph
from flowgraph.application.workflow_io import load_workflow, save_workflow
from flowgraph.application.workflow_session import WorkflowSession


def test_scalar_schema_and_defaults_are_inferred_without_execution():
    code = """raise RuntimeError("must not execute")
def Execute(mesh: MeshDocument, flag: bool=True, count: int=-2,
            scale: float=3, text: str="hello, world") -> tuple[()]:
    return ()
"""
    node = USER_FUNCTION.create_instance("python", parameters={"code": code})
    schema = USER_FUNCTION.parameters_for_instance(node)[1:]
    assert [(p.input_port, p.kind.id, p.default) for p in schema] == [
        ("flag", "boolean", True),
        ("count", "integer", -2),
        ("scale", "float", 3.0),
        ("text", "string", "hello, world"),
    ]
    assert [(p.name, p.is_param) for p in USER_FUNCTION.ports_for_instance(node)] == [
        ("mesh", False),
        ("flag", True),
        ("count", True),
        ("scale", True),
        ("text", True),
    ]


def test_scalar_inputs_without_declared_defaults():
    code = "def Execute(flag: bool, count: int, scale: float, text: str) -> tuple[bool, int, float, str]:\n    return (flag, count, scale, text)"
    assert USER_FUNCTION.executor({}, {"code": code}) == {
        "output1": False,
        "output2": 0,
        "output3": 0.0,
        "output4": "",
    }


def test_saved_values_connections_and_round_trip(tmp_path):
    registry = create_node_registry()
    code = "def Execute(code: str='source', scale: float=2.0) -> tuple[str, float]:\n    return (code, scale)"
    node = USER_FUNCTION.create_instance(
        "python",
        parameters={
            "code": code,
            "__user_input__code": "configured",
            "__user_input__scale": 4.0,
        },
    )
    graph = WorkflowGraph([node, SET_FLOAT.create_instance("source", parameters={"value": 9.0})])
    assert WorkflowExecutor(registry).run(graph).node_outputs["python"] == {
        "output1": "configured",
        "output2": 4.0,
    }
    edge = WorkflowEdge("source", "value", "python", "scale")
    graph.add_edge(edge, registry)
    assert WorkflowExecutor(registry).run(graph).node_outputs["python"]["output2"] == 9.0
    assert node.parameters["code"] == code
    assert node.parameters["__user_input__scale"] == 4.0
    path = tmp_path / "function.json"
    save_workflow(graph, path)
    loaded = load_workflow(path, registry)
    assert WorkflowExecutor(registry).run(loaded).node_outputs["python"]["output1"] == "configured"
    graph.remove_edge(edge, registry)
    node.parameters["__user_input__scale"] = 5.0
    assert WorkflowExecutor(registry).run(graph).node_outputs["python"]["output2"] == 5.0


@pytest.mark.parametrize("default", ["True", "'wrong'", "None", "dangerous()"])
def test_invalid_scalar_defaults_are_rejected_without_execution(default):
    code = f"def Execute(count: int={default}) -> tuple[int]:\n    return (count,)"
    node = USER_FUNCTION.create_instance("python", parameters={"code": code})
    with pytest.raises((ValueError, TypeError), match="default"):
        USER_FUNCTION.ports_for_instance(node)


def test_invalid_saved_type_and_signature_changes():
    code = "def Execute(value: int=2) -> tuple[int]:\n    return (value,)"
    with pytest.raises(TypeError, match="expected Integer"):
        USER_FUNCTION.executor({}, {"code": code, "__user_input__value": True})
    node = USER_FUNCTION.create_instance("python", parameters={"code": code})
    node.parameters["code"] = "def Execute(text: str='new') -> tuple[str]:\n    return (text,)"
    assert [p.input_port for p in USER_FUNCTION.parameters_for_instance(node)[1:]] == ["text"]


def test_session_preserves_authored_fallback():
    registry = create_node_registry()
    node = USER_FUNCTION.create_instance(
        "python",
        parameters={
            "code": "def Execute(value: float=2.0) -> tuple[float]:\n    return (value,)",
            "__user_input__value": 4.0,
        },
    )
    graph = WorkflowGraph([node, SET_FLOAT.create_instance("source", parameters={"value": 8.0})])
    edge = WorkflowEdge("source", "value", "python", "value")
    graph.add_edge(edge, registry)
    session = WorkflowSession(registry)
    session.run(graph)
    assert node.parameters["__user_input__value"] == 4.0
    graph.remove_edge(edge, registry)
    assert session.run(graph).node_outputs["python"]["output1"] == 4.0


def test_exported_scalar_input_uses_saved_or_literal_default():
    from flowgraph.application.workflow_defaults import saved_input_default

    registry = create_node_registry()
    node = USER_FUNCTION.create_instance(
        "python",
        parameters={
            "code": "def Execute(code: str='literal') -> tuple[str]:\n    return (code,)",
        },
    )
    graph = WorkflowGraph([node])
    graph.export_input("text", "python", "code", registry)
    port = graph.input("text")
    assert saved_input_default(graph, port)[0] == "literal"
    node.parameters["__user_input__code"] = "saved"
    assert saved_input_default(graph, port)[0] == "saved"
