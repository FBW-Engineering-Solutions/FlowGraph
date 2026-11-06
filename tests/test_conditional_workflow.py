"""Named composites and exclusive child execution regression tests."""

import json
from copy import deepcopy

import pytest

from flowgraph.adapters.data_types import STRING
from flowgraph.adapters.workflow import CONDITIONAL_WORKFLOW, RUN_WORKFLOW
from flowgraph.application.workflow_core import (
    NodeDefinition,
    NodeExecutionError,
    NodeInstance,
    NodeRegistry,
    PortDefinition,
    PortDirection,
    WorkflowEdge,
    WorkflowExecutor,
    WorkflowGraph,
)
from flowgraph.application.workflow_io import (
    WorkflowPersistenceError,
    workflow_from_dict,
    workflow_from_json,
    workflow_to_dict,
)


def test_connected_boolean_selects_child():
    from flowgraph.adapters.data_types import BOOLEAN

    registry, graph, _node, calls = setup_branches()
    registry.register(
        NodeDefinition(
            "selector",
            "",
            "Selector",
            (PortDefinition("value", PortDirection.OUTPUT, BOOLEAN),),
            lambda _inputs, _parameters, _context: {"value": True},
        )
    )
    graph.add_node(NodeInstance("A", "selector"))
    graph.add_edge(WorkflowEdge("A", "value", "branch", "condition"), registry)
    result = WorkflowExecutor(registry, parallel_tasks=3).run(graph)
    assert calls == ["true"]
    assert result.node_outputs["E"]["value"] == "true!!"


def test_nested_conditional_executes_only_selected_descendants():
    registry, graph, node, calls = setup_branches()
    _registry, _graph, inner, _calls = setup_branches()
    inner.id = "inner"
    inner.parameters["condition"] = True
    child = WorkflowGraph([inner])
    child.export_output("value", "inner", "value", registry)
    node.subworkflows["false"] = child
    result = WorkflowExecutor(registry, parallel_tasks=3).run(graph)
    assert calls == ["true"]
    assert result.node_outputs["E"]["value"] == "true!!"


def test_public_inputs_are_forwarded_to_selected_child():
    registry, graph, node, calls = setup_branches()
    for child in node.subworkflows.values():
        child.remove_node("F")
        child.export_input("text", "D", "value", registry)
    result = WorkflowExecutor(registry, parallel_tasks=3).run(
        graph,
        initial_inputs={"branch": {"text": "supplied", "condition": True}},
    )
    assert calls == []
    assert result.node_outputs["E"]["value"] == "supplied!!"


def test_cli_reports_code_in_both_alternatives_and_rejects_conflicting_defaults():
    from flowgraph.adapters.simple_sources import SET_STRING
    from flowgraph.adapters.user_code import USER_FUNCTION
    from flowgraph.application.node_registry import create_node_registry
    from flowgraph.application.workflow_cli import _arbitrary_code_nodes, format_workflow_inspection
    from flowgraph.application.workflow_defaults import saved_input_default

    registry = create_node_registry()
    node = CONDITIONAL_WORKFLOW.create_instance("branch")
    for key, child in node.subworkflows.items():
        child.add_node(SET_STRING.create_instance("text", parameters={"value": key}))
        child.add_node(USER_FUNCTION.create_instance("code"))
        child.export_input("text", "text", "value", registry)
    graph = WorkflowGraph([node])
    graph.export_input("text", "branch", "text", registry)
    warnings = _arbitrary_code_nodes(graph, registry)
    assert any("branch/false/code" in warning for warning in warnings)
    assert any("branch/true/code" in warning for warning in warnings)
    rendered = format_workflow_inspection(graph, registry)
    assert "subworkflow 'false':" in rendered
    assert "subworkflow 'true':" in rendered
    with pytest.raises(ValueError, match="Conflicting saved parameter"):
        saved_input_default(graph, graph.inputs[0])
    node.subworkflows["true"].require_node("text").parameters["value"] = "false"
    value, addresses = saved_input_default(graph, graph.inputs[0])
    assert value == "false"
    assert set(addresses) == {"branch/false/text.value", "branch/true/text.value"}


def test_invalid_mutated_keys_and_recursive_named_children_cannot_be_saved():
    _registry, graph, node, _calls = setup_branches()
    node.subworkflows[True] = WorkflowGraph()
    with pytest.raises(WorkflowPersistenceError, match="string keys"):
        workflow_to_dict(graph)
    del node.subworkflows[True]
    node.subworkflows["true"] = graph
    with pytest.raises(WorkflowPersistenceError, match="recursive"):
        workflow_to_dict(graph)


def test_ambiguous_legacy_and_named_children_are_rejected():
    registry, graph, _node, _calls = setup_branches()
    payload = workflow_to_dict(graph)
    payload["nodes"][0]["subworkflow"] = workflow_to_dict(WorkflowGraph())
    with pytest.raises(WorkflowPersistenceError, match="no legacy child"):
        workflow_from_dict(payload, registry)


def setup_branches():
    calls = []
    registry = NodeRegistry()
    registry.register(CONDITIONAL_WORKFLOW)
    registry.register(RUN_WORKFLOW)

    def source(_inputs, parameters, context):
        calls.append(parameters["name"])
        assert context.parallel_tasks == 3
        if parameters.get("fail"):
            raise ValueError("selected failure")
        return {"value": parameters["name"]}

    registry.register(
        NodeDefinition(
            "source",
            "",
            "Source",
            (PortDefinition("value", PortDirection.OUTPUT, STRING),),
            source,
        )
    )
    registry.register(
        NodeDefinition(
            "combine",
            "",
            "Combine",
            (
                PortDefinition("value", PortDirection.INPUT, STRING),
                PortDefinition("value", PortDirection.OUTPUT, STRING),
            ),
            lambda inputs, _parameters, _context: {"value": inputs["value"] + "!"},
        )
    )
    conditional = CONDITIONAL_WORKFLOW.create_instance("branch")
    for key, child in conditional.subworkflows.items():
        child.add_node(NodeInstance("F", "source", {"name": key}))
        child.add_node(NodeInstance("D", "combine"))
        child.add_edge(WorkflowEdge("F", "value", "D", "value"), registry)
        child.export_output("value", "D", "value", registry)
    graph = WorkflowGraph([conditional, NodeInstance("E", "combine")])
    graph.add_edge(WorkflowEdge("branch", "value", "E", "value"), registry)
    return registry, graph, conditional, calls


@pytest.mark.parametrize("condition", [False, True])
def test_only_selected_child_and_its_producer_execute_then_join(condition):
    registry, graph, node, calls = setup_branches()
    node.parameters["condition"] = condition
    inactive = node.subworkflows["false" if condition else "true"]
    inactive.require_node("F").parameters["fail"] = True
    result = WorkflowExecutor(registry, parallel_tasks=3).run(graph)
    case = "true" if condition else "false"
    assert calls == [case]
    assert result.execution_order == ("branch", "E")
    assert result.node_outputs["E"]["value"] == case + "!!"
    assert result.node_outputs["branch"]["result"].execution_order == ("F", "D")


def test_changing_selector_does_not_reuse_previous_child_outputs():
    registry, graph, _node, calls = setup_branches()
    executor = WorkflowExecutor(registry, parallel_tasks=3)
    first = executor.run(graph)
    second = executor.run(
        graph, initial_outputs=first.node_outputs, initial_inputs={"branch": {"condition": True}}
    )
    assert calls == ["false", "true"]
    assert second.node_outputs["E"]["value"] == "true!!"


def test_selected_failure_does_not_fall_back_or_execute_continuation():
    registry, graph, node, calls = setup_branches()
    node.subworkflows["false"].require_node("F").parameters["fail"] = True
    with pytest.raises(NodeExecutionError, match="selected failure") as caught:
        WorkflowExecutor(registry, parallel_tasks=3).run(graph)
    assert calls == ["false"]
    assert "E" not in caught.value.partial_result.node_outputs


def test_mismatched_interfaces_and_non_boolean_selectors_are_rejected():
    registry, graph, node, _calls = setup_branches()
    node.parameters["condition"] = 1
    with pytest.raises(NodeExecutionError, match="must be a boolean"):
        WorkflowExecutor(registry).run(graph)
    node.subworkflows["true"] = WorkflowGraph()
    with pytest.raises(NodeExecutionError, match="matching outputs"):
        WorkflowExecutor(registry).run(graph)


def test_named_children_round_trip_and_have_independent_factories():
    registry, graph, node, _calls = setup_branches()
    restored = workflow_from_json(json.dumps(workflow_to_dict(graph)), registry)
    assert set(restored.require_node("branch").subworkflows) == {"false", "true"}
    assert workflow_to_dict(restored) == workflow_to_dict(graph)
    other = CONDITIONAL_WORKFLOW.create_instance("other")
    assert other.subworkflows["true"] is not node.subworkflows["true"]
    assert other.subworkflows["true"] is not other.subworkflows["false"]


def test_version_two_single_child_migrates_to_default():
    registry, _graph, node, _calls = setup_branches()
    parent = RUN_WORKFLOW.create_instance("run")
    parent.subworkflows["default"] = node.subworkflows["false"]
    payload = workflow_to_dict(WorkflowGraph([parent]))
    payload["version"] = 2
    raw = payload["nodes"][0]
    raw["subworkflow"] = raw.pop("subworkflows")["default"]
    restored = workflow_from_dict(payload, registry)
    assert set(restored.require_node("run").subworkflows) == {"default"}
    assert workflow_to_dict(restored)["version"] == 3


@pytest.mark.parametrize("children", [{True: {}}, {1: {}}, {"": {}}, []])
def test_invalid_child_keys_rejected_in_memory_and_persistence(children):
    with pytest.raises(ValueError, match="string keys"):
        NodeInstance("invalid", "conditional-workflow", subworkflows=children)
    registry, graph, _node, _calls = setup_branches()
    payload = deepcopy(workflow_to_dict(graph))
    payload["nodes"][0]["subworkflows"] = children
    with pytest.raises(WorkflowPersistenceError, match="string keys"):
        workflow_from_dict(payload, registry)
