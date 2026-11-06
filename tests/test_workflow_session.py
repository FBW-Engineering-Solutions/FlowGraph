"""Incremental execution correctness is measured with calls, not wall clocks."""

from dataclasses import replace

import pytest

from flowgraph.application.workflow_core import (
    DataType,
    NodeDefinition,
    NodeExecutionError,
    NodeInstance,
    NodeRegistry,
    PortDefinition,
    PortDirection,
    WorkflowEdge,
    WorkflowGraph,
)
from flowgraph.application.workflow_session import WorkflowSession

TEXT = DataType("text", "Text", str)


@pytest.mark.parametrize("upstream", ["missing", "none"])
def test_debug_selection_reuses_valid_always_upstream(upstream):
    registry, graph, calls = setup_graph()
    registry._definitions["source"] = replace(registry.require("source"), cache_policy="always")
    session = WorkflowSession(registry)
    session.run(graph)
    calls.clear()
    session.run(graph, targets={"c"}, force={"c"}, upstream=upstream)
    assert calls == ["c"]
    assert set(session.metadata["reused"]) == {"a", "b"}


def test_no_upstream_execution_blocks_outdated_results_and_keeps_independent_successes():
    registry, graph, calls = setup_graph()
    session = WorkflowSession(registry)
    session.run(graph)
    calls.clear()
    graph.require_node("a").parameters["value"] = "changed"
    with pytest.raises(NodeExecutionError, match="missing or outdated"):
        session.run(graph, targets={"c"}, force={"c"}, upstream="none")
    assert calls == []
    assert "c" in session.metadata["blocked"]
    assert not session.entries
    session.run(graph, targets={"c"}, force={"c"}, upstream="missing")
    assert calls == ["source", "b", "c"]


def test_no_upstream_execution_runs_selected_dependencies_in_order():
    registry, graph, calls = setup_graph()
    session = WorkflowSession(registry)
    session.run(graph)
    calls.clear()
    session.run(graph, targets={"b", "c"}, force={"b", "c"}, upstream="none")
    assert calls == ["b", "c"]


def test_missing_only_reuses_valid_always_nodes():
    registry, graph, calls = setup_graph()
    registry._definitions["source"] = replace(registry.require("source"), cache_policy="always")
    session = WorkflowSession(registry)
    session.run(graph)
    calls.clear()
    session.run(graph, missing_only=True, upstream="missing")
    assert calls == []


def test_no_upstream_execution_checks_external_file_changes(tmp_path):
    registry, graph, calls = setup_graph()
    path = tmp_path / "input"
    path.write_text("before")
    registry._definitions["source"] = replace(
        registry.require("source"),
        cache_policy="external",
        cache_dependencies=lambda _i, _p: path.read_text(),
    )
    session = WorkflowSession(registry)
    session.run(graph)
    calls.clear()
    path.write_text("after")
    with pytest.raises(NodeExecutionError, match="missing or outdated"):
        session.run(graph, targets={"c"}, force={"c"}, upstream="none")
    assert calls == []
    assert "a" in session.metadata["invalidated"]
    assert not session.entries


def setup_graph():
    calls = []

    def source(_inputs, parameters):
        calls.append("source")
        return {"value": parameters.get("value", "hello")}

    def transform(inputs, parameters):
        calls.append(parameters["name"])
        if parameters.get("fail"):
            raise ValueError("failed")
        return {"value": inputs["value"].upper()}

    registry = NodeRegistry()
    registry.register(
        NodeDefinition(
            "source",
            "",
            "Source",
            (PortDefinition("value", PortDirection.OUTPUT, TEXT),),
            source,
            cache_policy="pure",
        )
    )
    registry.register(
        NodeDefinition(
            "transform",
            "",
            "Transform",
            (
                PortDefinition("value", PortDirection.INPUT, TEXT),
                PortDefinition("value", PortDirection.OUTPUT, TEXT),
            ),
            transform,
            cache_policy="pure",
        )
    )
    graph = WorkflowGraph(
        [
            NodeInstance("a", "source"),
            NodeInstance("b", "transform", {"name": "b"}),
            NodeInstance("c", "transform", {"name": "c"}),
            NodeInstance("d", "transform", {"name": "d"}),
        ],
        [
            WorkflowEdge("a", "value", "b", "value"),
            WorkflowEdge("b", "value", "c", "value"),
            WorkflowEdge("b", "value", "d", "value"),
        ],
    )
    return registry, graph, calls


def test_warm_cache_parameter_invalidation_and_independent_branch():
    registry, graph, calls = setup_graph()
    session = WorkflowSession(registry)
    session.run(graph)
    assert set(calls) == {"source", "b", "c", "d"}
    calls.clear()
    result = session.run(graph)
    assert calls == []
    assert result.execution_order == ()
    assert result.node_outputs["d"] == {"value": "HELLO"}
    assert len(session.metadata["reused"]) == 4
    graph.require_node("c").parameters["name"] = "changed"
    session.run(graph)
    assert calls == ["changed"]
    calls.clear()
    graph.require_node("b").parameters["name"] = "new b"
    session.run(graph)
    assert set(calls) == {"new b", "changed", "d"}


def test_selection_includes_missing_dependencies_and_leaves_other_branch_stale():
    registry, graph, calls = setup_graph()
    session = WorkflowSession(registry)
    session.run(graph, targets={"c"})
    assert calls == ["source", "b", "c"]
    calls.clear()
    session.run(graph)
    assert calls == ["d"]
    calls.clear()
    graph.require_node("b").parameters["name"] = "new b"
    session.run(graph, targets={"c"})
    assert calls == ["new b", "c"]
    assert "d" not in session.entries
    calls.clear()
    session.run(graph)
    assert calls == ["d"]


@pytest.mark.parametrize("policy", ["always", "external", "composite"])
def test_selected_run_preserves_untouched_nonpure_branch_and_rechecks_it_when_selected(policy):
    registry, graph, calls = setup_graph()
    dependency = ["first"]
    registry.register(
        replace(
            registry.require("transform"),
            id="other-branch",
            cache_policy=policy,
            cache_dependencies=(lambda _inputs, _parameters: dependency[0])
            if policy == "external"
            else None,
        )
    )
    graph.require_node("d").definition_id = "other-branch"
    session = WorkflowSession(registry)
    session.run(graph)
    old = session.entries["d"]
    calls.clear()
    dependency[0] = "changed outside the selected branch"
    result = session.run(graph, targets={"c"})
    assert calls == []
    assert result.node_outputs["d"]["value"] == "HELLO"
    assert session.entries["d"] is old
    assert "d" not in session.metadata["invalidated"]
    assert "d" in session.metadata["outside_scope"]
    assert "d" not in session.metadata["reused"]
    session.run(graph, targets={"d"})
    assert calls == ["d"]


def test_selected_json_response_keeps_completed_nonpure_sibling(monkeypatch):
    import json
    from collections import OrderedDict

    from flowgraph.application import workflow_execution

    registry, graph, calls = setup_graph()
    registry.register(replace(registry.require("transform"), id="action", cache_policy="always"))
    graph.require_node("d").definition_id = "action"
    monkeypatch.setattr(workflow_execution, "_REGISTRY", registry)
    # Reconstruct the graph on each JSON request, like native and WASM transports.
    payload = json.dumps(
        {
            "format": "flowgraph-workflow",
            "version": 3,
            "nodes": [
                {"id": n.id, "definition_id": n.definition_id, "parameters": n.parameters}
                for n in graph.nodes
            ],
            "edges": [
                {
                    "source_node": e.source_node,
                    "source_port": e.source_port,
                    "target_node": e.target_node,
                    "target_port": e.target_port,
                }
                for e in graph.edges
            ],
        }
    )
    monkeypatch.setattr(workflow_execution, "_SESSIONS", OrderedDict())
    first = json.loads(
        workflow_execution.execute_workflow_json(payload, {"session_id": "branches"})
    )
    assert first["status"] == "ok"
    calls.clear()
    selected = json.loads(
        workflow_execution.execute_workflow_json(
            payload, {"session_id": "branches", "targets": ["c"]}
        )
    )
    assert selected["status"] == "ok"
    assert calls == []
    assert selected["nodes"]["outputs"]["d"]["value"] == "HELLO"
    assert "d" in selected["display_inputs"]
    assert "d" not in selected["cache"]["invalidated"]


def test_force_invalidates_downstream_and_from_scratch_executes_all():
    registry, graph, calls = setup_graph()
    session = WorkflowSession(registry)
    session.run(graph)
    calls.clear()
    session.run(graph, targets={"b"}, force={"b"})
    assert calls == ["b"]
    assert set(session.entries) == {"a", "b"}
    calls.clear()
    session.run(graph, from_scratch=True)
    assert set(calls) == {"source", "b", "c", "d"}


def test_failure_never_falls_back_to_cached_outputs_and_keeps_independent_results():
    registry, graph, calls = setup_graph()
    session = WorkflowSession(registry)
    session.run(graph)
    graph.require_node("b").parameters["fail"] = True
    with pytest.raises(NodeExecutionError) as caught:
        session.run(graph)
    assert set(caught.value.partial_result.node_outputs) == {"a"}
    assert set(session.entries) == {"a"}
    assert set(session.metadata["blocked"]) == {"c", "d"}
    calls.clear()
    with pytest.raises(NodeExecutionError):
        session.run(graph)
    assert calls == ["b"]


def test_positions_do_not_invalidate_and_new_output_consumption_does():
    registry, graph, calls = setup_graph()
    session = WorkflowSession(registry)
    session.run(graph)
    calls.clear()
    graph.require_node("a").x = 42
    session.run(graph)
    assert not calls
    graph.export_output("out", "c", "value", registry)
    session.run(graph)
    assert calls == ["c"]


def test_rewire_invalidates_receiving_node():
    registry, graph, calls = setup_graph()
    session = WorkflowSession(registry)
    session.run(graph)
    calls.clear()
    rewired = WorkflowGraph(
        list(graph.nodes),
        [
            WorkflowEdge("a", "value", "b", "value"),
            WorkflowEdge("a", "value", "c", "value"),
            WorkflowEdge("b", "value", "d", "value"),
        ],
    )
    session.run(rewired)
    assert calls == ["c"]


def test_opaque_injected_inputs_are_never_reused_and_scalars_are():
    registry, graph, calls = setup_graph()
    graph = WorkflowGraph([graph.require_node("b")])
    session = WorkflowSession(registry)
    session.run(graph, initial_inputs={"b": {"value": "hi"}})
    calls.clear()
    session.run(graph, initial_inputs={"b": {"value": "hi"}})
    assert not calls
    session.run(graph, initial_inputs={"b": {"value": "other"}})
    assert calls == ["b"]


def test_entry_eviction_recomputes_dependencies():
    registry, graph, calls = setup_graph()
    session = WorkflowSession(registry, max_entries=1)
    session.run(graph)
    assert len(session.entries) == 1
    calls.clear()
    session.run(graph)
    assert set(calls) == {"source", "b", "c", "d"}


def test_always_execute_actions_do_not_suppress_writes_or_discard_safe_sources():
    registry, graph, calls = setup_graph()
    action = replace(registry.require("transform"), id="action", cache_policy="always")
    registry.register(action)
    graph.require_node("c").definition_id = "action"
    session = WorkflowSession(registry)
    session.run(graph)
    calls.clear()
    session.run(graph)
    assert calls == ["c"]


def test_failed_always_action_preserves_readonly_upstream_and_other_branch():
    registry, graph, calls = setup_graph()
    registry.register(replace(registry.require("transform"), id="action", cache_policy="always"))
    graph.require_node("c").definition_id = "action"
    session = WorkflowSession(registry)
    session.run(graph)
    calls.clear()
    graph.require_node("c").parameters["fail"] = True
    with pytest.raises(NodeExecutionError) as caught:
        session.run(graph, targets={"c"})
    assert calls == ["c"]
    assert set(session.entries) == {"a", "b", "d"}
    assert set(caught.value.partial_result.node_outputs) == {"a", "b", "d"}


def test_clear_and_separate_sessions():
    registry, graph, calls = setup_graph()
    first = WorkflowSession(registry)
    first.run(graph)
    epoch = first.epoch
    first.clear()
    assert first.epoch != epoch
    assert not first.entries
    second = WorkflowSession(registry)
    calls.clear()
    second.run(graph)
    assert len(calls) == 4


def test_unknown_targets_and_force_outside_scope_are_rejected():
    registry, graph, _ = setup_graph()
    session = WorkflowSession(registry)
    with pytest.raises(KeyError):
        session.run(graph, targets={"missing"})
    with pytest.raises(ValueError):
        session.run(graph, targets={"b"}, force={"d"})


def test_file_content_not_just_metadata_invalidates_and_deletion_never_reuses(tmp_path):
    import os

    from flowgraph.application.file_dependencies import single_file_dependency

    path = tmp_path / "input.txt"
    path.write_text("first")
    registry, graph, calls = setup_graph()

    def read(_inputs, parameters):
        calls.append("read")
        return {"value": path.read_text()}

    registry.register(
        replace(
            registry.require("source"),
            id="reader",
            executor=read,
            cache_policy="external",
            cache_dependencies=single_file_dependency,
        )
    )
    graph.require_node("a").definition_id = "reader"
    graph.require_node("a").parameters["path"] = str(path)
    session = WorkflowSession(registry)
    session.run(graph)
    calls.clear()
    session.run(graph)
    assert calls == []
    original = path.stat()
    path.write_text("other")
    os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
    result = session.run(graph)
    assert result.node_outputs["c"]["value"] == "OTHER"
    assert "read" in calls
    path.unlink()
    with pytest.raises(NodeExecutionError):
        session.run(graph)
    assert not session.entries


def test_nested_sessions_reuse_children_and_do_not_skip_child_actions():
    from flowgraph.adapters.workflow import RUN_WORKFLOW

    registry, child, calls = setup_graph()
    registry.register(RUN_WORKFLOW)
    child.export_output("value", "c", "value", registry)
    outer = RUN_WORKFLOW.create_instance("outer")
    outer.subworkflow = child
    graph = WorkflowGraph([outer])
    session = WorkflowSession(registry)
    session.run(graph)
    calls.clear()
    session.run(graph)
    assert not calls
    assert session.metadata["executed"] == ["outer"]
    registry.register(replace(registry.require("transform"), id="action", cache_policy="always"))
    child.require_node("d").definition_id = "action"
    session.run(graph)
    calls.clear()
    session.run(graph)
    assert calls == ["d"]


def test_connected_parameter_execution_does_not_cause_permanent_misses():
    from flowgraph.application.node_registry import create_node_registry

    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            registry.create_instance("set-string", "source", parameters={"value": "hello"}),
            registry.create_instance("set-string", "target", parameters={"value": "authored"}),
        ],
        [WorkflowEdge("source", "value", "target", "value")],
    )
    session = WorkflowSession(registry)
    session.run(graph)
    assert graph.require_node("target").parameters["value"] == "authored"
    result = session.run(graph)
    assert not result.execution_order


def test_conditional_keeps_branch_namespaces_isolated():
    from flowgraph.adapters.workflow import CONDITIONAL_WORKFLOW

    registry, _child, calls = setup_graph()
    registry.register(CONDITIONAL_WORKFLOW)
    outer = CONDITIONAL_WORKFLOW.create_instance("conditional")
    for key in ("true", "false"):
        branch = WorkflowGraph([NodeInstance("a", "source", {"value": key})])
        branch.export_output("value", "a", "value", registry)
        outer.subworkflows[key] = branch
    session = WorkflowSession(registry)
    graph = WorkflowGraph([outer])
    assert session.run(graph).node_outputs["conditional"]["value"] == "false"
    calls.clear()
    session.run(graph)
    assert calls == []
    outer.parameters["condition"] = True
    assert session.run(graph).node_outputs["conditional"]["value"] == "true"
    assert calls == ["source"]
    calls.clear()
    outer.parameters["condition"] = False
    assert session.run(graph).node_outputs["conditional"]["value"] == "false"
    assert not calls


def test_batch_reuses_iterations_and_invalidates_changed_scalar_inputs():
    from flowgraph.adapters.workflow import BATCH_WORKFLOW

    registry, _, calls = setup_graph()
    registry.register(BATCH_WORKFLOW)
    child = WorkflowGraph([NodeInstance("b", "transform", {"name": "b"})])
    child.export_input("text", "b", "value", registry)
    child.export_output("value", "b", "value", registry)
    batch = BATCH_WORKFLOW.create_instance("batch")
    batch.subworkflow = child
    graph = WorkflowGraph([batch])
    session = WorkflowSession(registry)
    result = session.run(graph, initial_inputs={"batch": {"text": ["one", "two"]}})
    assert result.node_outputs["batch"]["value"] == ["ONE", "TWO"]
    assert calls == ["b", "b"]
    calls.clear()
    session.run(graph, initial_inputs={"batch": {"text": ["one", "two"]}})
    assert not calls
    session.run(graph, initial_inputs={"batch": {"text": ["one", "changed"]}})
    assert calls == ["b"]


def test_child_edit_invalidates_parent_descendants_even_outside_scope():
    from flowgraph.adapters.workflow import RUN_WORKFLOW

    registry, _, _calls = setup_graph()
    registry.register(RUN_WORKFLOW)
    child = WorkflowGraph([NodeInstance("a", "source")])
    child.export_output("value", "a", "value", registry)
    outer = RUN_WORKFLOW.create_instance("outer")
    outer.subworkflow = child
    graph = WorkflowGraph(
        [
            outer,
            NodeInstance("sink", "transform", {"name": "sink"}),
            NodeInstance("independent", "source"),
        ],
        [WorkflowEdge("outer", "value", "sink", "value")],
    )
    session = WorkflowSession(registry)
    session.run(graph)
    child.require_node("a").parameters["value"] = "changed"
    result = session.run(graph, targets={"independent"})
    assert "sink" not in result.node_outputs
    assert "sink" not in session.entries


def test_unconnected_parameter_restores_authored_value_after_disconnect():
    from flowgraph.application.node_registry import create_node_registry

    registry = create_node_registry()
    source = registry.create_instance("set-string", "source", parameters={"value": "wired"})
    target = registry.create_instance("set-string", "target", parameters={"value": "authored"})
    session = WorkflowSession(registry)
    session.run(
        WorkflowGraph([source, target], [WorkflowEdge("source", "value", "target", "value")])
    )
    result = session.run(WorkflowGraph([source, target]))
    assert result.node_outputs["target"]["value"] == "authored"


def test_timestamp_change_invalidates_before_hash_and_tracks_unlisted_companion(
    tmp_path, monkeypatch
):
    import os
    from pathlib import Path

    from flowgraph.application.file_dependencies import single_file_dependency

    principal = tmp_path / "principal"
    companion = tmp_path / "companion"
    principal.write_text("companion")
    companion.write_text("before")
    registry, graph, calls = setup_graph()

    def read(_inputs, _parameters):
        calls.append("read")
        return {"value": companion.read_text()}

    registry.register(
        replace(
            registry.require("source"),
            id="reader",
            executor=read,
            cache_policy="external",
            cache_dependencies=single_file_dependency,
        )
    )
    graph.require_node("a").definition_id = "reader"
    graph.require_node("a").parameters["path"] = str(principal)
    session = WorkflowSession(registry)
    session.run(graph)
    calls.clear()
    companion.write_text("after")
    info = principal.stat()
    os.utime(principal, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))
    original_open = Path.open

    def checked_open(path, *args, **kwargs):
        if path == principal and args and args[0] == "rb":
            assert "read" in calls, "Changed timestamp must invalidate before hashing"
        return original_open(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", checked_open)
        result = session.run(graph)
    assert result.node_outputs["c"]["value"] == "AFTER"
    assert calls == ["read", "b", "c", "d"]
    calls.clear()
    session.run(graph)
    assert calls == []


def test_unchanged_metadata_still_checks_content(tmp_path, monkeypatch):
    from flowgraph.application import file_dependencies

    path = tmp_path / "data"
    path.write_text("before")
    registry, graph, calls = setup_graph()
    registry.register(
        replace(
            registry.require("source"),
            id="reader",
            cache_policy="external",
            cache_dependencies=file_dependencies.single_file_dependency,
        )
    )
    graph.require_node("a").definition_id = "reader"
    graph.require_node("a").parameters["path"] = str(path)
    # Freeze ALL metadata, so only the digest can reveal the edit.
    metadata = file_dependencies._file_metadata(path)
    monkeypatch.setattr(file_dependencies, "_file_metadata", lambda _path: metadata)
    session = WorkflowSession(registry)
    session.run(graph)
    calls.clear()
    path.write_text("edited")
    session.run(graph)
    assert calls == ["source", "b", "c", "d"]
