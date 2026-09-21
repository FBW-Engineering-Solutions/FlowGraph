import json
from pathlib import Path

import pytest

from flowgraph.adapters.simple_sources import SET_STRING
from flowgraph.adapters.workflow import BATCH_WORKFLOW, RUN_WORKFLOW
from flowgraph.adapters.workflow_interfaces import WORKFLOW_INPUT, WORKFLOW_OUTPUT
from flowgraph.application.node_registry import (
    create_initial_workflow,
    create_node_registry,
)
from flowgraph.application.workflow_core import (
    DataType,
    NodeDefinition,
    NodeRegistry,
    PortDefinition,
    PortDirection,
    WorkflowEdge,
    WorkflowGraph,
)
from flowgraph.application.workflow_io import (
    WorkflowPersistenceError,
    execute_workflow_file,
    load_workflow,
    save_workflow,
    workflow_from_dict,
    workflow_from_json,
    workflow_to_dict,
)
from flowgraph.resources import package_resource_path


def test_workflow_json_round_trip_preserves_domain_graph(tmp_path: Path) -> None:
    registry = create_node_registry()
    workflow = create_initial_workflow()
    workflow.require_node("file-path").parameters["path"] = "fixtures/source.mesh"
    destination = tmp_path / "workflow.json"

    saved_path = save_workflow(workflow, destination)
    restored = load_workflow(destination, registry)

    assert saved_path == destination.resolve()
    assert workflow_to_dict(restored) == workflow_to_dict(workflow)
    assert destination.read_text().endswith("\n")
    assert (
        destination.read_text()
        == json.dumps(workflow_to_dict(workflow), indent=2, sort_keys=True) + "\n"
    )


@pytest.mark.parametrize("filename", ("SimpleReadMesh.json", "AllFilters.json"))
def test_packaged_demo_workflows_load(filename: str) -> None:
    workflow = load_workflow(package_resource_path("testdata", filename), create_node_registry())

    assert workflow.nodes
    assert workflow.edges


def test_documentation_title_is_portless_and_persists_its_text() -> None:
    registry = create_node_registry()
    title = registry.create_instance(
        "title-doc", "section-title", parameters={"title": "Import mesh"}
    )
    workflow = WorkflowGraph([title])

    restored = workflow_from_dict(workflow_to_dict(workflow), registry)

    definition = registry.require("title-doc")
    assert definition.ports == ()
    assert restored.require_node("section-title").parameters == {"title": "Import mesh"}


def test_documentation_paragraph_is_portless_and_persists_its_text() -> None:
    registry = create_node_registry()
    paragraph = registry.create_instance(
        "paragraph-doc", "notes", parameters={"text": "First paragraph.\n\nSecond paragraph."}
    )
    workflow = WorkflowGraph([paragraph])

    restored = workflow_from_dict(workflow_to_dict(workflow), registry)

    definition = registry.require("paragraph-doc")
    assert definition.ports == ()
    assert restored.require_node("notes").parameters == {
        "text": "First paragraph.\n\nSecond paragraph."
    }


def test_workflow_boundary_nodes_persist_their_public_interface() -> None:
    registry = create_node_registry()
    workflow = WorkflowGraph(
        [
            WORKFLOW_INPUT.create_instance("input", parameters={"name": "value"}),
            WORKFLOW_OUTPUT.create_instance("output", parameters={"name": "result"}),
        ]
    )
    workflow.add_edge(WorkflowEdge("input", "value", "output", "value"), registry)
    workflow.sync_boundary_nodes(registry)

    restored = workflow_from_dict(workflow_to_dict(workflow), registry)

    assert [port.name for port in restored.inputs] == ["value"]
    assert [port.name for port in restored.outputs] == ["result"]
    assert restored.execute({"value": "hello"}, registry) == {"result": "hello"}


def test_display_value_sink_persists_its_input_connection() -> None:
    registry = create_node_registry()
    source = registry.create_instance("set-int", "source", parameters={"value": 7})
    display = registry.create_instance("show-value", "display")
    workflow = WorkflowGraph([source, display])
    workflow.add_edge(WorkflowEdge("source", "value", "display", "value"), registry)

    restored = workflow_from_dict(workflow_to_dict(workflow), registry)

    assert restored.require_node("display").definition_id == "show-value"
    assert restored.edges == workflow.edges


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda payload: payload.update(format="other"), "Unsupported workflow format"),
        (lambda payload: payload.update(version=99), "Unsupported workflow version"),
        (
            lambda payload: payload["nodes"][0].update(definition_id="missing"),
            "unknown definition",
        ),
        (
            lambda payload: payload["edges"][0].update(source_port="missing"),
            "Invalid edge",
        ),
    ],
)
def test_workflow_loader_rejects_unsupported_or_invalid_graphs(change, message) -> None:  # type: ignore[no-untyped-def]
    payload = workflow_to_dict(create_initial_workflow())
    change(payload)

    with pytest.raises(WorkflowPersistenceError, match=message):
        workflow_from_dict(payload, create_node_registry())


def test_workflow_loader_allows_incomplete_graph_for_later_editing() -> None:
    registry = create_node_registry()
    workflow = WorkflowGraph([registry.create_instance("load-muscat", "loader")])

    restored = workflow_from_dict(workflow_to_dict(workflow), registry)

    assert restored.require_node("loader").definition_id == "load-muscat"


def test_non_json_parameters_are_rejected() -> None:
    workflow = create_initial_workflow()
    workflow.require_node("file-path").parameters["bad"] = object()

    with pytest.raises(WorkflowPersistenceError, match="cannot be represented as JSON"):
        workflow_to_dict(workflow)


def test_load_workflow_reports_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(WorkflowPersistenceError, match="not valid JSON"):
        load_workflow(path, create_node_registry())


def test_workflow_from_json_loads_browser_provided_text() -> None:
    workflow = create_initial_workflow()
    content = json.dumps(workflow_to_dict(workflow))

    restored = workflow_from_json(content, create_node_registry(), source_name="dropped.json")

    assert workflow_to_dict(restored) == workflow_to_dict(workflow)


def test_workflow_loader_resolves_testdata_paths_without_changing_json() -> None:
    payload = workflow_to_dict(create_initial_workflow())
    payload["nodes"][0]["parameters"]["path"] = "{testdata}/FlowGraph.stl"

    restored = workflow_from_dict(payload, create_node_registry())

    path = Path(restored.require_node("file-path").parameters["path"])
    assert path == Path(__file__).parents[1] / "src" / "flowgraph" / "testdata" / "FlowGraph.stl"
    assert payload["nodes"][0]["parameters"]["path"] == "{testdata}/FlowGraph.stl"


def test_workflow_export_replaces_packaged_testdata_paths_with_token() -> None:
    workflow = workflow_from_json(
        json.dumps(
            {
                "format": "flowgraph-workflow",
                "version": 1,
                "nodes": [
                    {
                        "id": "file-path",
                        "definition_id": "select-file",
                        "parameters": {"path": "{testdata}/FlowGraph.stl"},
                        "position": {"x": 0, "y": 0},
                    }
                ],
                "edges": [],
            }
        ),
        create_node_registry(),
    )

    exported = workflow_to_dict(workflow)

    assert exported["nodes"][0]["parameters"]["path"] == "{testdata}/FlowGraph.stl"


def test_workflow_export_leaves_unrelated_absolute_paths_unchanged() -> None:
    workflow = create_initial_workflow()
    path = "/tmp/external/FlowGraph.stl"
    workflow.require_node("file-path").parameters["path"] = path

    exported = workflow_to_dict(workflow)

    assert exported["nodes"][0]["parameters"]["path"] == path


def test_workflow_from_json_resolves_nested_testdata_paths() -> None:
    payload = workflow_to_dict(create_initial_workflow())
    payload["nodes"][0]["parameters"]["path"] = ["{testdata}/FlowGraph.stl"]

    restored = workflow_from_json(json.dumps(payload), create_node_registry())

    assert restored.require_node("file-path").parameters["path"] == [
        str(Path(__file__).parents[1] / "src" / "flowgraph" / "testdata" / "FlowGraph.stl")
    ]


def test_workflow_from_json_reports_dropped_filename_for_malformed_json() -> None:
    with pytest.raises(WorkflowPersistenceError, match=r"dropped\.json.*not valid JSON"):
        workflow_from_json("{not-json", create_node_registry(), source_name="dropped.json")


def test_execute_workflow_file_applies_overrides_without_mutating_file(
    tmp_path: Path,
) -> None:
    text = DataType("text", "Text", str)
    seen: list[str] = []
    source = NodeDefinition(
        "source",
        "mdi-source",
        "Source",
        (PortDefinition("value", PortDirection.OUTPUT, text),),
        lambda _inputs, parameters: {"value": parameters["value"]},
        default_parameters={"value": "saved"},
    )
    sink = NodeDefinition(
        "sink",
        "mdi-sink",
        "Sink",
        (PortDefinition("value", PortDirection.INPUT, text),),
        lambda inputs, _parameters: seen.append(inputs["value"]) or {},
    )
    registry = NodeRegistry()
    registry.register(source)
    registry.register(sink)
    workflow = WorkflowGraph([source.create_instance("input"), sink.create_instance("output")])
    workflow.add_edge(WorkflowEdge("input", "value", "output", "value"), registry)
    path = tmp_path / "executable.json"
    save_workflow(workflow, path)
    original_json = path.read_text()

    result = execute_workflow_file(path, {"input": {"value": "runtime"}}, registry=registry)

    assert result.node_outputs["input"] == {"value": "runtime"}
    assert seen == ["runtime"]
    assert path.read_text() == original_json


def test_execute_workflow_file_rejects_unknown_override_node(tmp_path: Path) -> None:
    path = tmp_path / "workflow.json"
    save_workflow(create_initial_workflow(), path)

    with pytest.raises(WorkflowPersistenceError, match="unknown node"):
        execute_workflow_file(path, {"missing": {"path": "mesh.mesh"}})


def test_workflow_json_round_trip_preserves_exported_interface() -> None:
    registry = NodeRegistry()
    text = DataType("text", "Text", str)
    definition = NodeDefinition(
        "transform",
        "",
        "Transform",
        (
            PortDefinition("value", PortDirection.INPUT, text),
            PortDefinition("result", PortDirection.OUTPUT, text),
        ),
        lambda inputs, _parameters: {"result": inputs["value"]},
    )
    registry.register(definition)
    graph = WorkflowGraph([definition.create_instance("transform")])
    graph.add_input("value", "transform", "value", registry)
    graph.add_output("result", "transform", "result", registry)

    restored = workflow_from_dict(workflow_to_dict(graph), registry)

    assert [(p.name, p.node_id, p.node_port) for p in restored.inputs] == [
        ("value", "transform", "value")
    ]
    assert [(p.name, p.node_id, p.node_port) for p in restored.outputs] == [
        ("result", "transform", "result")
    ]
    assert restored.execute({"value": "ok"}, registry) == {"result": "ok"}


def test_workflow_json_round_trip_preserves_nested_workflow_structure() -> None:
    registry = create_node_registry()
    child = WorkflowGraph(
        [
            WORKFLOW_INPUT.create_instance("input", parameters={"name": "value"}),
            WORKFLOW_OUTPUT.create_instance("output", parameters={"name": "result"}),
        ]
    )
    child.add_edge(WorkflowEdge("input", "value", "output", "value"), registry)
    child.sync_boundary_nodes(registry)
    composite = RUN_WORKFLOW.create_instance("nested")
    composite.subworkflow = child
    workflow = WorkflowGraph([composite])

    restored = workflow_from_dict(workflow_to_dict(workflow), registry)
    restored_node = restored.require_node("nested")

    assert workflow_to_dict(restored) == workflow_to_dict(workflow)
    assert restored_node.subworkflow is not None
    assert [port.name for port in restored_node.subworkflow.inputs] == ["value"]
    assert [port.name for port in restored_node.subworkflow.outputs] == ["result"]


def test_workflow_json_round_trip_preserves_batch_workflow_structure() -> None:
    registry = create_node_registry()
    child = WorkflowGraph([WORKFLOW_INPUT.create_instance("input", parameters={"name": "value"})])
    child.sync_boundary_nodes(registry)
    batch = BATCH_WORKFLOW.create_instance("batch")
    batch.subworkflow = child

    restored = workflow_from_dict(workflow_to_dict(WorkflowGraph([batch])), registry)
    restored_node = restored.require_node("batch")

    assert restored_node.definition_id == "batch-workflow"
    assert restored_node.subworkflow is not None
    assert [port.name for port in restored_node.subworkflow.inputs] == ["value"]


def test_version_one_json_backed_run_workflow_migrates_to_a_child_graph() -> None:
    registry = create_node_registry()
    child = WorkflowGraph([SET_STRING.create_instance("source", parameters={"value": "nested"})])
    legacy_payload = {
        "format": "flowgraph-workflow",
        "version": 1,
        "nodes": [
            {
                "id": "nested",
                "definition_id": "run-workflow",
                "parameters": {"workflow": json.dumps(workflow_to_dict(child))},
                "position": {"x": 0, "y": 0},
            }
        ],
        "inputs": [],
        "outputs": [],
        "edges": [],
    }

    restored = workflow_from_dict(legacy_payload, registry)
    restored_node = restored.require_node("nested")

    assert restored_node.parameters == {}
    assert restored_node.subworkflow is not None
    assert restored_node.subworkflow.require_node("source").parameters == {"value": "nested"}
    assert workflow_to_dict(restored)["version"] == 2
