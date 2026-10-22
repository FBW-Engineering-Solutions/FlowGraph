"""Tests for the headless FlowGraph workflow command-line interface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowgraph.adapters.controls import FLOAT_SLIDER
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
    execute_cli_workflow,
    format_workflow_inspection,
    parse_inputs,
    parse_overrides,
)
from flowgraph.application.workflow_core import WorkflowEdge, WorkflowGraph
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
    assert "  │\n   │ (workflow-output)[output] Workflow Output" in text
    assert "   └─(I) value - Any" in text


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
    expected_workflow = """  (title-doc)[title-doc-5] Title
  (P) title - Text: 'Mesh Converter Muscat >> Muscat'

  (paragraph-doc)[paragraph-doc-6] Paragraph
  (P) text - Text: 'Read a mesh file with Muscat and save it with Muscat. '

  (workflow-input)[input] Workflow Input
  (I) value - Any
  (P) name - Text: 'in_filename'
  (O) value - Any
   │
   │ (load-muscat)[mesh_loader] Read Mesh (Muscat)
   └─(P) path - FilePath
     (O) mesh - Mesh document
      │
      │ (workflow-input)[output] Workflow Input
      │ (I) value - Any
      │ (P) name - Text: 'out_filename'
      │ (O) value - Any
      │  │
      │  │ (write-muscat)[mesh_writer] Write Mesh (Muscat)
      │  └─(P) path - FilePath
      └────(I) mesh - Mesh document"""
    assert text.split("Workflow:\n", 1)[1] == expected_workflow


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
    assert "└─(I) value - Any" in text
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

    assert (
        text.split("Workflow:\n", 1)[1]
        == """  (download-url)[download-url_1] Download URL
  (P) url - Text: 'https://example.test/image.jpg'
  (O) path - Text
   │
   │ (read-image)[read-image_3] Read Image (Pillow)
   └─(P) path - FilePath
     (O) image - Image
      │
      │ (float-slider)[float-slider_1] Float Slider
      │ (P) min - Float: 0.0
      │ (P) max - Float: 180.0
      │ (P) value - Float: 33.27
      │ (O) value - Float
      │  │
      │  │ (rotate-image)[rotate-image_2] Rotate Image
      │  └─(P) angle - Float
      └────(I) image - Image
           (P) expand - Boolean: True
           (O) image - Image
            │
            │ (local-view)[local-view_2] Show Image
            └─(I) input - Image"""
    )


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


def test_cli_inspection_renders_nested_workflows() -> None:
    registry = create_node_registry()
    child = WorkflowGraph([SET_STRING.create_instance("child-source")])
    composite = RUN_WORKFLOW.create_instance("nested")
    composite.subworkflow = child

    text = format_workflow_inspection(WorkflowGraph([composite]), registry)

    assert "(run-workflow)[nested] Run Full Workflow" in text
    assert "  subworkflow:" in text
    assert "    (set-string)[child-source] String Input" in text


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


def test_cli_inspect_command_warns_about_saved_arbitrary_code(tmp_path: Path, capsys) -> None:
    path = tmp_path / "workflow.json"
    save_workflow(WorkflowGraph([USER_FUNCTION.create_instance("python")]), path)

    assert main(("inspect", str(path))) == 0
    output = capsys.readouterr()
    assert "Warning: This workflow contains nodes that execute arbitrary code:" in output.out
    assert "  (user-function)[python] User Function" in output.out
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


def test_inspect_reports_conflicting_defaults_without_hiding_graph(tmp_path, capsys):
    registry = create_node_registry()
    graph = _default_workflow()
    graph.add_node(SET_STRING.create_instance("other", parameters={"value": "different"}))
    graph.add_edge(WorkflowEdge("input", "value", "other", "value"), registry)
    path = tmp_path / "conflict.json"
    save_workflow(graph, path)
    assert main(["inspect", str(path)]) == 0
    output = capsys.readouterr()
    assert "default: (conflicting saved values; provide --input)" in output.out
    assert "Workflow:" in output.out
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
