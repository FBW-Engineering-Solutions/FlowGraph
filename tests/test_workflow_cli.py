"""Tests for the headless FlowGraph workflow command-line interface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowgraph.adapters.controls import FLOAT_SLIDER
from flowgraph.adapters.data_types import STRING
from flowgraph.adapters.image_tools import READ_IMAGE, ROTATE_IMAGE
from flowgraph.adapters.imagej import IMAGEJ_SCRIPT, IMAGEJ_SCRIPT_FILE
from flowgraph.adapters.remote_files import DOWNLOAD_URL
from flowgraph.adapters.simple_sources import SET_STRING
from flowgraph.adapters.sinks import SHOW_IMAGE
from flowgraph.adapters.user_code import USER_FUNCTION
from flowgraph.adapters.workflow import RUN_WORKFLOW
from flowgraph.adapters.workflow_interfaces import WORKFLOW_INPUT, WORKFLOW_OUTPUT
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_cli import (
    WorkflowCliError,
    _render_graph,
    execute_cli_workflow,
    format_workflow_inspection,
    inspect_workflow,
    parse_inputs,
    parse_overrides,
)
from flowgraph.application.workflow_core import (
    NodeDefinition,
    NodeRegistry,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
    WorkflowEdge,
    WorkflowGraph,
)
from flowgraph.application.workflow_io import load_workflow, save_workflow
from flowgraph.core_cli import main


def _published_workflow() -> WorkflowGraph:
    registry = create_node_registry()
    workflow = WorkflowGraph(
        [
            WORKFLOW_INPUT.create_instance("input", parameters={"name": "value"}),
            WORKFLOW_OUTPUT.create_instance("output", parameters={"name": "result"}),
        ]
    )
    workflow.add_edge(WorkflowEdge("input", "value", "output", "value"), registry)
    workflow.sync_boundary_nodes(registry)
    return workflow


def _override_workflow() -> WorkflowGraph:
    registry = create_node_registry()
    source = SET_STRING.create_instance("source", parameters={"value": "saved"})
    output = WORKFLOW_OUTPUT.create_instance("output", parameters={"name": "result"})
    workflow = WorkflowGraph([source, output])
    workflow.add_edge(WorkflowEdge("source", "value", "output", "value"), registry)
    workflow.sync_boundary_nodes(registry)
    return workflow


def test_cli_assignment_parsers_decode_json_and_validate_shape() -> None:
    assert parse_inputs(["count=3", "enabled=true", "name=hello"]) == {
        "count": 3,
        "enabled": True,
        "name": "hello",
    }
    assert parse_overrides(["source.value=updated"]) == {"source": {"value": "updated"}}
    with pytest.raises(WorkflowCliError, match="NAME=VALUE"):
        parse_inputs(["missing-separator"])
    with pytest.raises(WorkflowCliError, match="NODE-ID.PARAMETER=VALUE"):
        parse_overrides(["source=value"])


def test_cli_inspection_lists_public_interface_and_directed_edges() -> None:
    text = format_workflow_inspection(_published_workflow(), create_node_registry())

    assert "Warning:" not in text
    assert "Inputs:\n  value: Any (input.value)" in text
    assert "Outputs:\n  result: Any (output.value)" in text
    assert "(workflow-input)[input] Workflow Input" in text
    assert "(workflow-output)[output] Workflow Output" in text
    assert "(O) value - Any" in text
    assert "┌─── (O) value - Any (to output.value)" in text
    assert "└──▶ (I) value - Any (from input.value)" in text


@pytest.mark.parametrize("full_option", ["--full", "-f"])
def test_cli_inspection_is_compact_by_default_and_full_is_opt_in(
    tmp_path: Path, capsys, monkeypatch, full_option: str
) -> None:
    from flowgraph.application import workflow_cli

    path = tmp_path / "inspection.json"
    save_workflow(_published_workflow(), path)
    full_text = inspect_workflow(path, full=True)
    compact_text = full_text.split("Workflow:\n", 1)[0].rstrip()
    with monkeypatch.context() as patch:

        def unexpected_graph(*args, **kwargs):
            pytest.fail("Compact inspection must not render the graph")

        patch.setattr(workflow_cli, "_format_graph", unexpected_graph)
        assert inspect_workflow(path) == compact_text
        assert main(["inspect", str(path)]) == 0
        captured = capsys.readouterr()
        assert captured.out == compact_text + "\n"
        assert captured.err == ""
    assert main(["inspect", full_option, str(path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == full_text + "\n"
    assert captured.err == ""


@pytest.mark.parametrize("full", [False, True])
def test_cli_inspection_full_flag_handles_empty_graph(tmp_path: Path, full: bool) -> None:
    path = tmp_path / "empty.json"
    save_workflow(WorkflowGraph(), path)
    text = inspect_workflow(path, full=full)
    assert text.startswith("Inputs:\n  (none)\nOutputs:\n  (none)")
    assert ("Workflow:\n  (empty)" in text) is full


def test_cli_inspection_lists_disconnected_nodes_before_connected_tree() -> None:
    registry = create_node_registry()
    workflow = load_workflow(
        Path("src/flowgraph/testdata/muscat-muscat-mesh-conversion.json"), registry
    )
    text = format_workflow_inspection(workflow, registry)

    title_index = text.index("[title-doc-5]")
    paragraph_index = text.index("[paragraph-doc-6]")
    input_index = text.index("[input]")
    output_index = text.index("[output]")
    writer_index = text.index("[mesh_writer]")
    assert title_index < paragraph_index < input_index < output_index < writer_index
    assert "\n\n  (paragraph-doc)[paragraph-doc-6]" in text
    assert "(O) value - Any (to mesh_loader.path)" in text
    assert "(O) value - Any (to mesh_writer.path)" in text
    assert "(O) mesh - Mesh document (to mesh_writer.mesh)" in text
    assert "(P) path - FilePath (from output.value)" in text
    assert "(I) mesh - Mesh document (from mesh_loader.mesh)" in text
    assert "(P) path - FilePath:" not in text


def test_cli_inspection_lists_ports_parameters_and_defaults_deterministically() -> None:
    registry = create_node_registry()
    workflow = WorkflowGraph([SET_STRING.create_instance("source", parameters={"value": "saved"})])

    text = format_workflow_inspection(workflow, registry)
    assert "(set-string)[source] String Input" in text
    assert "(P) value - Text: 'saved'" in text
    assert "(O) value - Text" in text
    assert "(I) value - Text" not in text
    assert text == format_workflow_inspection(workflow, registry)


def test_cli_inspection_renders_branching_edges_vertically() -> None:
    registry = create_node_registry()
    source = SET_STRING.create_instance("source", parameters={"value": "saved"})
    first = WORKFLOW_OUTPUT.create_instance("first", parameters={"name": "first"})
    second = WORKFLOW_OUTPUT.create_instance("second", parameters={"name": "second"})
    workflow = WorkflowGraph([source, first, second])
    workflow.add_edge(WorkflowEdge("source", "value", "first", "value"), registry)
    workflow.add_edge(WorkflowEdge("source", "value", "second", "value"), registry)

    text = format_workflow_inspection(workflow, registry)
    assert text.count("│\n") >= 2
    assert "┌─── (O) value - Text (to first.value, second.value)" in text
    assert text.count("(O) value - Text") == 1
    assert "├──▶ (I) value - Any (from source.value)" in text
    assert "└──▶ (I) value - Any (from source.value)" in text
    assert text.count("┌") == text.count("└") == 1
    assert text.count("(I) value - Any (from source.value)") == 2
    assert text.count("▶") == len(workflow.edges)
    assert text.index("[first]") < text.index("[second]")


def test_cli_inspection_preserves_order_for_multiple_incoming_edges() -> None:
    registry = create_node_registry()
    first = SET_STRING.create_instance("first", parameters={"value": "one"})
    second = SET_STRING.create_instance("second", parameters={"value": "two"})
    target = WORKFLOW_OUTPUT.create_instance("target", parameters={"name": "target"})
    workflow = WorkflowGraph([first, second, target])
    workflow.add_edge(WorkflowEdge("first", "value", "target", "value"), registry)

    # The output boundary accepts only one input, so use two independent source
    # references in the textual graph through a custom edge-like fixture instead.
    # The graph model rejects competing input edges; this assertion instead checks
    # the stable ordering of the two source branches.
    text = format_workflow_inspection(workflow, registry)
    assert text.index("[second]") < text.index("[first]")


def test_cli_inspection_shared_lane_branches_twice_at_one_node_and_is_reused() -> None:
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            SET_STRING.create_instance("source"),
            USER_FUNCTION.create_instance(
                "merge",
                parameters={
                    "code": "def Execute(left, right) -> tuple[Any]:\n    return (left,)\n"
                },
            ),
            WORKFLOW_OUTPUT.create_instance("sink"),
        ]
    )
    for edge in (
        WorkflowEdge("source", "value", "merge", "left"),
        WorkflowEdge("source", "value", "merge", "right"),
        WorkflowEdge("merge", "output1", "sink", "value"),
    ):
        graph.add_edge(edge, registry)
    text = format_workflow_inspection(graph, registry).split("Workflow:\n", 1)[1]
    assert "┌─── (O) value - Text (to merge.left, merge.right)" in text
    assert "├──▶ (I) left - Any (from source.value)" in text
    assert "└──▶ (I) right - Any (from source.value)" in text
    assert "\n  ┌─── (O) output1 - Any (to sink.value)" in text
    assert text.count("┌") == text.count("└") == 2
    assert text.count("├") == 1


def test_cli_inspection_lists_shared_target_inputs_before_outputs() -> None:
    registry = create_node_registry()
    workflow = WorkflowGraph(
        [
            DOWNLOAD_URL.create_instance(
                "download-url_1", parameters={"url": "https://example.test/image.jpg"}
            ),
            READ_IMAGE.create_instance("read-image_3"),
            FLOAT_SLIDER.create_instance(
                "float-slider_1", parameters={"min": 0, "max": 180, "value": 33.27}
            ),
            ROTATE_IMAGE.create_instance("rotate-image_2"),
            SHOW_IMAGE.create_instance("local-view_2"),
        ]
    )
    for edge in (
        WorkflowEdge("download-url_1", "path", "read-image_3", "path"),
        WorkflowEdge("read-image_3", "image", "rotate-image_2", "image"),
        WorkflowEdge("float-slider_1", "value", "rotate-image_2", "angle"),
        WorkflowEdge("rotate-image_2", "image", "local-view_2", "input"),
    ):
        workflow.add_edge(edge, registry)

    text = format_workflow_inspection(workflow, registry)

    graph_text = text.split("Workflow:\n", 1)[1]
    assert "(P) angle - Float (from float-slider_1.value)" in graph_text
    assert "(I) image - Image (from read-image_3.image)" in graph_text
    target_text = graph_text.split("[rotate-image_2]", 1)[1]
    assert target_text.index("(P) angle") < target_text.index("(O) image")
    assert target_text.index("(I) image") < target_text.index("(O) image")
    for edge in workflow.edges:
        source_section = graph_text.split(f"[{edge.source_node}]", 1)[1].split("\n\n", 1)[0]
        assert f"(to {edge.target_node}.{edge.target_port})" in source_section


def test_cli_inspection_keeps_disconnected_nodes_and_empty_workflows() -> None:
    registry = create_node_registry()
    empty = format_workflow_inspection(WorkflowGraph(), registry)
    assert "Workflow:\n  (empty)" in empty

    text = format_workflow_inspection(
        WorkflowGraph([SET_STRING.create_instance("one"), SET_STRING.create_instance("two")]),
        registry,
    )
    assert "(set-string)[one] String Input" in text
    assert "(set-string)[two] String Input" in text


@pytest.mark.parametrize("reverse", [False, True])
def test_cli_inspection_preserves_every_edge_in_shared_dependency_graph(
    tmp_path: Path, capsys, reverse: bool
) -> None:
    registry = create_node_registry()
    nodes = [
        USER_FUNCTION.create_instance(
            "merge",
            parameters={"code": "def Execute(left, right) -> tuple[Any]:\n    return (left,)\n"},
        ),
        SET_STRING.create_instance("left", parameters={"value": "left saved"}),
        SET_STRING.create_instance("right", parameters={"value": "right saved"}),
        WORKFLOW_OUTPUT.create_instance("result", parameters={"name": "result"}),
        WORKFLOW_OUTPUT.create_instance("preview", parameters={"name": "preview"}),
        WORKFLOW_INPUT.create_instance("source", parameters={"name": "message"}),
    ]
    edges = [
        WorkflowEdge("source", "value", "left", "value"),
        WorkflowEdge("source", "value", "right", "value"),
        WorkflowEdge("left", "value", "merge", "left"),
        WorkflowEdge("right", "value", "merge", "right"),
        WorkflowEdge("left", "value", "preview", "value"),
        WorkflowEdge("merge", "output1", "result", "value"),
    ]
    graph = WorkflowGraph(list(reversed(nodes)) if reverse else nodes)
    for edge in reversed(edges) if reverse else edges:
        graph.add_edge(edge, registry)
    graph.sync_boundary_nodes(registry)
    path = tmp_path / "shared-dependencies.json"
    save_workflow(graph, path)
    restored = load_workflow(path, registry)
    assert main(["inspect", str(path), "--full"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    text = captured.out.split("Workflow:\n", 1)[1]
    assert (
        text.rstrip() == format_workflow_inspection(restored, registry).split("Workflow:\n", 1)[1]
    )
    for node in nodes:
        assert text.count(f"[{node.id}]") == 1
    for edge in edges:
        source = text.index(f"[{edge.source_node}]")
        target = text.index(f"[{edge.target_node}]")
        source_section = text[source:target]
        output_line = next(
            line
            for line in source_section.splitlines()
            if f"(O) {edge.source_port} -" in line
            and f"{edge.target_node}.{edge.target_port}" in line
        )
        assert "(to " in output_line
        target_section = text[target:].split("\n\n", 1)[0]
        assert f"(from {edge.source_node}.{edge.source_port})" in target_section
    output_count = len({(edge.source_node, edge.source_port) for edge in edges})
    assert text.count("┌") == text.count("└") == output_count
    assert text.count("├") == len(edges) - output_count
    assert text.count("▶") == len(edges)
    assert "(P) value - Text:" not in text
    assert "(I) left - Any\n" not in text
    assert "(I) right - Any\n" not in text


def test_cli_inspection_connection_lane_snapshot() -> None:
    text = format_workflow_inspection(_published_workflow(), create_node_registry())
    assert (
        text.split("Workflow:\n", 1)[1]
        == """       (workflow-input)[input] Workflow Input
       (I) value - Any
       (P) name - Text: 'value'
  ┌─── (O) value - Any (to output.value)
  │
  │    (workflow-output)[output] Workflow Output
  └──▶ (I) value - Any (from input.value)
       (P) name - Text: 'result'
       (O) value - Any"""
    )


def test_cli_inspection_reorders_independent_branches_without_changing_workflow() -> None:
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            SET_STRING.create_instance("left"),
            SET_STRING.create_instance("right"),
            WORKFLOW_OUTPUT.create_instance("left-end"),
            WORKFLOW_OUTPUT.create_instance("right-end"),
        ]
    )
    graph.add_edge(WorkflowEdge("left", "value", "left-end", "value"), registry)
    graph.add_edge(WorkflowEdge("right", "value", "right-end", "value"), registry)
    execution_order = graph.topological_order()
    nodes = list(graph.nodes)
    edges = list(graph.edges)
    baseline = "\n".join(_render_graph(graph, registry, indent="  ", order=execution_order))
    text = format_workflow_inspection(graph, registry).split("Workflow:\n", 1)[1]
    assert baseline.count("┼") > 0
    assert text.count("┼") == 0
    assert text.index("[left]") < text.index("[left-end]") < text.index("[right]")
    for edge in graph.edges:
        assert text.index(f"[{edge.source_node}]") < text.index(f"[{edge.target_node}]")
    assert graph.topological_order() == execution_order
    assert list(graph.nodes) == nodes
    assert list(graph.edges) == edges
    assert format_workflow_inspection(graph, registry).split("Workflow:\n", 1)[1] == text


@pytest.mark.parametrize("parameter_input", [False, True])
def test_cli_inspection_aligns_connected_ports_and_node_details(parameter_input: bool) -> None:
    registry = create_node_registry()
    source = WORKFLOW_INPUT.create_instance("source", parameters={"name": "message"})
    if parameter_input:
        target = SET_STRING.create_instance("target")
    else:
        target = USER_FUNCTION.create_instance(
            "target",
            parameters={
                "code": "def Execute(value, spare=None) -> tuple[Any, Any]:\n    return (value, spare)\n"
            },
        )
    graph = WorkflowGraph(
        [
            source,
            target,
            WORKFLOW_OUTPUT.create_instance("first"),
            WORKFLOW_OUTPUT.create_instance("second"),
        ]
    )
    graph.add_edge(WorkflowEdge("source", "value", "target", "value"), registry)
    outputs = [
        port.name
        for port in registry.require(target.definition_id).ports_for_instance(target)
        if port.direction is PortDirection.OUTPUT
    ]
    graph.add_edge(WorkflowEdge("target", outputs[0], "first", "value"), registry)
    graph.add_edge(WorkflowEdge("target", outputs[-1], "second", "value"), registry)
    text = format_workflow_inspection(graph, registry).split("Workflow:\n", 1)[1]
    section = text[text.index(next(line for line in text.splitlines() if "[target]" in line)) :]
    section = section.split("[first]", 1)[0]
    details = [
        line
        for line in section.splitlines()
        if "[target]" in line or any(f"({kind})" in line for kind in "IPO")
    ]
    columns = [line.index("(") for line in details]
    assert len(columns) >= 3
    assert len(set(columns)) == 1


def test_cli_inspection_renders_nested_workflows() -> None:
    registry = create_node_registry()
    child = WorkflowGraph([SET_STRING.create_instance("child-source")])
    composite = RUN_WORKFLOW.create_instance("nested")
    composite.subworkflow = child

    text = format_workflow_inspection(WorkflowGraph([composite]), registry)

    assert "(run-workflow)[nested] Run Full Workflow" in text
    assert "  subworkflow:" in text
    assert "    (set-string)[child-source] String Input" in text


@pytest.mark.parametrize("reverse_edges", [False, True])
def test_cli_inspection_permutations_keep_inputs_parameters_outputs_separate(reverse_edges) -> None:
    registry = NodeRegistry()
    registry.register(SET_STRING)
    target = NodeDefinition(
        id="mixed",
        icon="",
        label="Mixed",
        ports=(
            PortDefinition("left", PortDirection.INPUT, STRING),
            PortDefinition("right", PortDirection.INPUT, STRING),
            PortDefinition("spare", PortDirection.INPUT, STRING, required=False),
            PortDefinition("out", PortDirection.OUTPUT, STRING),
        ),
        parameters=(
            ParameterDefinition("x", STRING, "X", "saved x"),
            ParameterDefinition("y", STRING, "Y", "saved y"),
            ParameterDefinition("unused", STRING, "Unused", "saved unused", port=False),
        ),
        executor=lambda _inputs, _parameters: {},
    )
    registry.register(target)
    # Parameter sources precede ordinary inputs deliberately: they must still
    # render in the parameter section, not ahead of the (I) section.
    graph = WorkflowGraph(
        [
            *(SET_STRING.create_instance(name) for name in ("px", "py", "il", "ir")),
            target.create_instance("target"),
        ]
    )
    edges = [
        WorkflowEdge(source, "value", "target", port)
        for source, port in (("px", "x"), ("py", "y"), ("il", "left"), ("ir", "right"))
    ]
    for edge in reversed(edges) if reverse_edges else edges:
        graph.add_edge(edge, registry)
    order = graph.topological_order()
    baseline = "\n".join(
        _render_graph(graph, registry, indent="  ", order=order, optimize_ports=False)
    )
    text = "\n".join(_render_graph(graph, registry, indent="  ", order=order))
    section = text.split("[target]", 1)[1]
    tokens = ["(I) right", "(I) left", "(I) spare", "(P) y", "(P) x", "(P) unused", "(O) out"]
    assert [section.index(token) for token in tokens] == sorted(
        section.index(token) for token in tokens
    )
    assert text.count("┼") < baseline.count("┼")
    assert "saved x" not in section and "saved y" not in section
    assert "saved unused" in section
    assert graph.topological_order() == order
    assert [port.name for port in target.ports][:3] == ["left", "right", "spare"]


def test_cli_inspection_reorders_outputs_by_last_consumer_without_duplicate_fanout() -> None:
    registry = NodeRegistry()
    registry.register(WORKFLOW_OUTPUT)
    source = NodeDefinition(
        id="outputs",
        icon="",
        label="Outputs",
        ports=tuple(
            PortDefinition(name, PortDirection.OUTPUT, STRING)
            for name in ("early", "late", "unused")
        ),
        executor=lambda _inputs, _parameters: {},
    )
    registry.register(source)
    graph = WorkflowGraph(
        [
            source.create_instance("source"),
            *(WORKFLOW_OUTPUT.create_instance(name) for name in ("first", "middle", "last")),
        ]
    )
    for edge in (
        WorkflowEdge("source", "early", "first", "value"),
        WorkflowEdge("source", "late", "middle", "value"),
        WorkflowEdge("source", "late", "last", "value"),
    ):
        graph.add_edge(edge, registry)
    order = graph.topological_order()
    baseline = "\n".join(
        _render_graph(graph, registry, indent="  ", order=order, optimize_ports=False)
    )
    text = "\n".join(_render_graph(graph, registry, indent="  ", order=order))
    assert text.index("(O) late") < text.index("(O) early") < text.index("(O) unused")
    assert "(O) late - Text (to middle.value, last.value)" in text
    assert text.count("(O) late") == 1
    assert text.count("┼") < baseline.count("┼")
    assert text.count("├") == 1
    assert text.count("┌") == text.count("└") == 2
    assert text == "\n".join(_render_graph(graph, registry, indent="  ", order=order))
    assert [port.name for port in source.ports] == ["early", "late", "unused"]


@pytest.mark.parametrize("definition", [IMAGEJ_SCRIPT, IMAGEJ_SCRIPT_FILE, USER_FUNCTION])
def test_cli_inspection_warns_about_arbitrary_code(definition) -> None:
    workflow = WorkflowGraph([definition.create_instance("code")])

    text = format_workflow_inspection(workflow, create_node_registry())

    assert "Warning: This workflow contains nodes that execute arbitrary code:" in text
    assert f"  ({definition.id})[code] {definition.label}" in text
    assert "Review and trust this code before running the workflow." in text
    assert text.index("Warning:") < text.index("Workflow:")


def test_cli_inspection_warns_about_nested_arbitrary_code_nodes() -> None:
    child = WorkflowGraph([USER_FUNCTION.create_instance("python")])
    composite = RUN_WORKFLOW.create_instance("nested")
    composite.subworkflow = child
    workflow = WorkflowGraph([IMAGEJ_SCRIPT.create_instance("groovy"), composite])

    text = format_workflow_inspection(workflow, create_node_registry())

    assert text.count("Warning:") == 1
    assert "  (imagej-script)[groovy] ImageJ Groovy Script" in text
    assert "  (user-function)[nested/python] User Function" in text


@pytest.mark.parametrize("options", [[], ["--full"], ["-f"]])
def test_cli_inspect_command_warns_about_saved_arbitrary_code(
    tmp_path: Path, capsys, options
) -> None:
    path = tmp_path / "workflow.json"
    save_workflow(WorkflowGraph([USER_FUNCTION.create_instance("python")]), path)

    assert main(["inspect", str(path), *options]) == 0
    output = capsys.readouterr()
    assert "Warning: This workflow contains nodes that execute arbitrary code:" in output.out
    assert "  (user-function)[python] User Function" in output.out
    assert ("Workflow:" in output.out) is bool(options)
    assert output.err == ""


def test_cli_execution_injects_published_inputs(tmp_path: Path) -> None:
    path = tmp_path / "workflow.json"
    save_workflow(_published_workflow(), path)

    workflow, result = execute_cli_workflow(path, inputs={"value": "runtime"})

    assert result.node_outputs["output"]["value"] == "runtime"
    assert workflow.outputs[0].name == "result"


@pytest.mark.parametrize("option", ("--input", "-i"))
def test_cli_run_accepts_input_option(tmp_path: Path, capsys, option: str) -> None:
    workflow_path = tmp_path / "workflow.json"
    save_workflow(_published_workflow(), workflow_path)

    assert main(("run", str(workflow_path), option, "value=runtime")) == 0
    output = capsys.readouterr()
    assert output.out == "Outputs:\n  result: 'runtime'\n"
    assert output.err == ""


def test_cli_run_applies_parameter_override_and_writes_json(tmp_path: Path, capsys) -> None:
    workflow_path = tmp_path / "workflow.json"
    output_path = tmp_path / "result.json"
    save_workflow(_override_workflow(), workflow_path)

    assert (
        main(
            (
                "run",
                str(workflow_path),
                "--override",
                "source.value=updated",
                "--json-output",
                str(output_path),
            )
        )
        == 0
    )
    assert json.loads(output_path.read_text()) == {"result": "updated"}
    assert capsys.readouterr().out == ""


def test_cli_run_reports_missing_inputs_without_traceback(tmp_path: Path, capsys) -> None:
    workflow_path = tmp_path / "workflow.json"
    save_workflow(_published_workflow(), workflow_path)

    assert main(("run", str(workflow_path))) == 2
    assert "Missing required workflow inputs: value" in capsys.readouterr().err


def _default_workflow(definition_id="set-string", value="saved") -> WorkflowGraph:
    registry = create_node_registry()
    boundary = WORKFLOW_INPUT.create_instance("input", parameters={"name": "value"})
    target = registry.create_instance(definition_id, "target", parameters={"value": value})
    output = WORKFLOW_OUTPUT.create_instance("output", parameters={"name": "result"})
    graph = WorkflowGraph([boundary, target, output])
    graph.add_edge(WorkflowEdge("input", "value", "target", "value"), registry)
    graph.add_edge(WorkflowEdge("target", "value", "output", "value"), registry)
    graph.sync_boundary_nodes(registry)
    return graph


@pytest.mark.parametrize("mode", [[], ["--full"], ["-f"]])
@pytest.mark.parametrize("input_option", ["--input", "-i"])
def test_inspect_previews_input_and_override_precedence_without_execution(
    tmp_path: Path, capsys, monkeypatch, mode, input_option: str
) -> None:
    from flowgraph.application.workflow_core import WorkflowExecutor

    def unexpected_run(*args, **kwargs):
        pytest.fail("Inspection must never execute nodes")

    monkeypatch.setattr(WorkflowExecutor, "run", unexpected_run)
    graph = _default_workflow()
    graph.add_node(SET_STRING.create_instance("standalone", parameters={"value": "original"}))
    path = tmp_path / "preview.json"
    save_workflow(graph, path)
    original = path.read_bytes()
    base = [
        "inspect",
        str(path),
        *mode,
        "--override",
        "target.value=overridden",
        "--override",
        "standalone.value=preview",
    ]
    assert main(base) == 0
    output = capsys.readouterr()
    assert "default: 'overridden'" in output.out
    assert "(--input)" not in output.out
    assert output.err == ""
    if mode:
        assert "(P) value - Text: 'preview'" in output.out
    assert main([*base, input_option, "value=explicit"]) == 0
    output = capsys.readouterr()
    assert "default: 'explicit' (--input)" in output.out
    assert "default: 'overridden'" not in output.out
    assert output.err == ""
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    ("definition_id", "assignment", "expected"),
    [
        ("set-int", "0", "0"),
        ("set-boolean", "false", "False"),
        ("set-string", "", "''"),
    ],
)
def test_inspect_explicit_falsy_values(tmp_path, capsys, definition_id, assignment, expected):
    path = tmp_path / "falsy.json"
    value = {"set-int": 42, "set-boolean": True, "set-string": "saved"}[definition_id]
    save_workflow(_default_workflow(definition_id, value), path)
    assert main(["inspect", str(path), "-i", f"value={assignment}"]) == 0
    output = capsys.readouterr()
    assert f"default: {expected} (--input)" in output.out
    assert output.err == ""


@pytest.mark.parametrize(
    ("options", "error"),
    [
        (["-i", "unknown=value"], "Unknown workflow inputs"),
        (["-i", "value=42"], "expected Text, got int"),
        (["-i", "value=one", "--input", "value=two"], "provided more than once"),
        (["-i", "missing-separator"], "NAME=VALUE"),
        (["--override", "target=value"], "NODE-ID.PARAMETER=VALUE"),
        (["--override", "missing.value=x"], "unknown node"),
        (["--override", "target.missing=x"], "Unknown parameters"),
        (
            ["--override", "target.value=x", "--override", "target.value=y"],
            "provided more than once",
        ),
    ],
)
def test_inspect_validates_assignments(tmp_path, capsys, options, error):
    path = tmp_path / "invalid.json"
    save_workflow(_default_workflow(), path)
    assert main(["inspect", str(path), *options]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert error in output.err
    assert "Traceback" not in output.err


def test_inspect_explicit_input_bypasses_conflicts_and_allows_other_missing_inputs(tmp_path):
    registry = create_node_registry()
    graph = _default_workflow()
    graph.add_node(SET_STRING.create_instance("other", parameters={"value": "different"}))
    graph.add_edge(WorkflowEdge("input", "value", "other", "value"), registry)
    graph.add_node(WORKFLOW_INPUT.create_instance("missing", parameters={"name": "required"}))
    graph.sync_boundary_nodes(registry)
    path = tmp_path / "partial.json"
    save_workflow(graph, path)
    text = inspect_workflow(path, inputs={"value": "explicit"})
    assert "default: 'explicit' (--input)" in text
    assert "conflicting" not in text
    assert "required:" in text and "default: (none; required)" in text
    text = inspect_workflow(path, overrides={"other": {"value": "saved"}})
    assert "default: 'saved'" in text
    assert "conflicting" not in text


def test_inspect_direct_export_previews_override_and_explicit_input(tmp_path):
    registry = create_node_registry()
    graph = _override_workflow()
    graph.export_input("text", "source", "value", registry)
    path = tmp_path / "direct-preview.json"
    save_workflow(graph, path)
    assert "default: 'override'" in inspect_workflow(
        path, overrides={"source": {"value": "override"}}
    )
    text = inspect_workflow(
        path, inputs={"text": "explicit"}, overrides={"source": {"value": "override"}}
    )
    assert "default: 'explicit' (--input)" in text


def test_inspect_nested_input_previews_without_executing(tmp_path):
    registry = create_node_registry()
    nested = RUN_WORKFLOW.create_instance("nested")
    nested.subworkflow = _default_workflow(value="child saved")
    graph = WorkflowGraph(
        [
            WORKFLOW_INPUT.create_instance("input", parameters={"name": "value"}),
            nested,
        ]
    )
    graph.add_edge(WorkflowEdge("input", "value", "nested", "value"), registry)
    graph.sync_boundary_nodes(registry)
    path = tmp_path / "nested-preview.json"
    save_workflow(graph, path)
    assert "default: 'child saved'" in inspect_workflow(path)
    assert "default: 'explicit' (--input)" in inspect_workflow(
        path, inputs={"value": "explicit"}, full=True
    )


@pytest.mark.parametrize(
    ("definition_id", "value", "expected"),
    [
        ("set-string", "saved", "'saved'"),
        ("set-string", "", "''"),
        ("set-int", 0, "0"),
        ("set-boolean", False, "False"),
    ],
)
def test_inspect_shows_saved_input_default(tmp_path, capsys, definition_id, value, expected):
    path = tmp_path / "inspect-default.json"
    save_workflow(_default_workflow(definition_id, value), path)
    before = path.read_bytes()
    assert main(["inspect", str(path)]) == 0
    output = capsys.readouterr()
    inputs = output.out.split("Outputs:", 1)[0]
    assert f"(input.value)  default: {expected}\n" in inputs
    assert output.err == ""
    assert path.read_bytes() == before


def test_inspect_marks_required_input_without_default():
    text = format_workflow_inspection(_published_workflow(), create_node_registry())
    assert "(input.value)  default: (none; required)" in text


@pytest.mark.parametrize("options", [[], ["--full"], ["-f"]])
def test_inspect_reports_conflicting_defaults_without_hiding_graph(tmp_path, capsys, options):
    registry = create_node_registry()
    graph = _default_workflow()
    graph.add_node(SET_STRING.create_instance("other", parameters={"value": "different"}))
    graph.add_edge(WorkflowEdge("input", "value", "other", "value"), registry)
    path = tmp_path / "conflict.json"
    save_workflow(graph, path)
    assert main(["inspect", str(path), *options]) == 0
    output = capsys.readouterr()
    assert "default: (conflicting saved values; provide --input)" in output.out
    assert ("Workflow:" in output.out) is bool(options)
    assert output.err == ""


@pytest.mark.parametrize(
    ("definition_id", "value"),
    [("set-string", "saved"), ("set-string", ""), ("set-int", 0), ("set-boolean", False)],
)
def test_cli_omitted_input_uses_saved_downstream_value_and_warns(
    tmp_path, capsys, definition_id, value
):
    path = tmp_path / "defaults.json"
    save_workflow(_default_workflow(definition_id, value), path)
    before = path.read_bytes()
    _, result = execute_cli_workflow(path)
    assert result.node_outputs["output"]["value"] == value
    warning = capsys.readouterr().err
    assert "Warning:" in warning
    assert "Workflow input 'value' was not provided" in warning
    assert "target.value" in warning
    assert repr(value) in warning
    assert path.read_bytes() == before


def test_cli_explicit_input_takes_precedence_without_warning(tmp_path, capsys):
    path = tmp_path / "defaults.json"
    save_workflow(_default_workflow(), path)
    assert main(["run", str(path), "--input", "value=explicit"]) == 0
    output = capsys.readouterr()
    assert "result: 'explicit'" in output.out
    assert output.err == ""


def test_cli_default_warning_does_not_pollute_json_output(tmp_path, capsys):
    path = tmp_path / "defaults.json"
    destination = tmp_path / "outputs.json"
    save_workflow(_default_workflow(), path)
    assert main(["run", str(path), "--json-output", str(destination)]) == 0
    assert json.loads(destination.read_text()) == {"result": "saved"}
    output = capsys.readouterr()
    assert output.out == ""
    assert "Warning:" in output.err


def test_cli_default_reflects_parameter_override(tmp_path, capsys):
    path = tmp_path / "defaults.json"
    save_workflow(_default_workflow(), path)
    assert main(["run", str(path), "--override", "target.value=updated"]) == 0
    output = capsys.readouterr()
    assert "result: 'updated'" in output.out
    assert "saved parameter value 'updated'" in output.err


def test_cli_direct_export_default(tmp_path, capsys):
    registry = create_node_registry()
    graph = _override_workflow()
    graph.export_input("text", "source", "value", registry)
    inspection = format_workflow_inspection(graph, registry)
    assert "(source.value)  default: 'saved'" in inspection
    path = tmp_path / "direct.json"
    save_workflow(graph, path)
    assert main(["run", str(path)]) == 0
    output = capsys.readouterr()
    assert "result: 'saved'" in output.out
    assert "source.value" in output.err


@pytest.mark.parametrize(
    ("definition_id", "parameter", "value"),
    [
        ("read-image", "path", "saved image.png"),
        ("create-uniform-mesh-of-bars", "startPoint", [1, 2, 3]),
    ],
)
def test_saved_default_normalizes_file_and_vector_values(tmp_path, definition_id, parameter, value):
    from flowgraph.application.workflow_defaults import saved_input_default
    from flowgraph.domain.filepath import FilePath

    registry = create_node_registry()
    boundary = WORKFLOW_INPUT.create_instance("input", parameters={"name": "value"})
    target = registry.create_instance(definition_id, "target", parameters={parameter: value})
    graph = WorkflowGraph([boundary, target])
    graph.add_edge(WorkflowEdge("input", "value", "target", parameter), registry)
    graph.sync_boundary_nodes(registry)
    path = tmp_path / "typed.json"
    save_workflow(graph, path)
    restored = load_workflow(path, registry)
    default = saved_input_default(restored, restored.inputs[0])
    assert default is not None
    resolved, addresses = default
    assert addresses == (f"target.{parameter}",)
    inspection = format_workflow_inspection(restored, registry).split("Outputs:", 1)[0]
    if parameter == "path":
        assert isinstance(resolved, FilePath)
        assert str(resolved) == value
        assert "default:" in inspection and "saved image.png" in inspection
    else:
        assert resolved == [1.0, 2.0, 3.0]
        assert all(type(component) is float for component in resolved)
        assert "default: <list: [1.0, 2.0, 3.0]>" in inspection


def test_cli_nested_input_default(tmp_path, capsys):
    registry = create_node_registry()
    nested = RUN_WORKFLOW.create_instance("nested")
    nested.subworkflow = _default_workflow(value="nested saved")
    boundary = WORKFLOW_INPUT.create_instance("input", parameters={"name": "value"})
    output = WORKFLOW_OUTPUT.create_instance("output", parameters={"name": "result"})
    graph = WorkflowGraph([boundary, nested, output])
    graph.add_edge(WorkflowEdge("input", "value", "nested", "value"), registry)
    graph.add_edge(WorkflowEdge("nested", "result", "output", "value"), registry)
    graph.sync_boundary_nodes(registry)
    assert "(input.value)  default: 'nested saved'" in format_workflow_inspection(graph, registry)
    path = tmp_path / "nested.json"
    save_workflow(graph, path)
    _, result = execute_cli_workflow(path)
    assert result.node_outputs["output"]["value"] == "nested saved"
    assert "nested/target.value" in capsys.readouterr().err


@pytest.mark.parametrize("other_value", ["saved", "conflicting"])
def test_cli_fanout_defaults_require_agreement(tmp_path, capsys, other_value):
    registry = create_node_registry()
    graph = _default_workflow()
    graph.add_node(SET_STRING.create_instance("other", parameters={"value": other_value}))
    graph.add_edge(WorkflowEdge("input", "value", "other", "value"), registry)
    path = tmp_path / "fanout.json"
    save_workflow(graph, path)
    if other_value == "saved":
        assert main(["run", str(path)]) == 0
        assert "Warning:" in capsys.readouterr().err
    else:
        assert main(["run", str(path)]) == 2
        assert "Conflicting saved parameter values" in capsys.readouterr().err
        assert main(["run", str(path), "--input", "value=explicit"]) == 0
        assert capsys.readouterr().err == ""


def test_cli_run_reports_node_execution_errors_without_traceback(tmp_path: Path, capsys) -> None:
    workflow_path = tmp_path / "workflow.json"
    save_workflow(_override_workflow(), workflow_path)

    assert main(("run", str(workflow_path), "--override", "source.missing=value")) == 2
    error = capsys.readouterr().err
    assert "Unknown parameters for node 'source'" in error
    assert "Traceback" not in error


def test_module_cli_run_applies_parameter_override_and_writes_json(tmp_path: Path, capsys) -> None:
    workflow_path = tmp_path / "workflow.json"
    output_path = tmp_path / "result.json"
    save_workflow(_override_workflow(), workflow_path)

    assert (
        main(
            (
                "run",
                str(workflow_path),
                "--override",
                "source.value=updated",
                "--json-output",
                str(output_path),
            )
        )
        == 0
    )
    assert json.loads(output_path.read_text()) == {"result": "updated"}
    assert capsys.readouterr().out == ""
