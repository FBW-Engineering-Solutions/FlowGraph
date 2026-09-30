"""Tests for script-derived ImageJ ports and the optional PyImageJ bridge."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from flowgraph.adapters import ADAPTERS
from flowgraph.adapters.data_types import FILE, IMAGEJ, STRING
from flowgraph.adapters.imagej import IMAGEJ_SCRIPT, IMAGEJ_SCRIPT_FILE
from flowgraph.application.workflow_core import (
    NodeDefinition,
    NodeRegistry,
    PortDefinition,
    PortDirection,
    WorkflowEdge,
    WorkflowExecutor,
    WorkflowGraph,
)
from flowgraph.domain.filepath import FilePath


def test_script_declarations_create_named_typed_ports_without_loading_imagej() -> None:
    instance = IMAGEJ_SCRIPT.create_instance(
        "script",
        parameters={
            "code": "#@ OpService ops\n#@ Dataset image\n#@ String label\n"
            "#@output Dataset processed\n#@output String title\n",
        },
    )
    ports = IMAGEJ_SCRIPT.ports_for_instance(instance)

    assert [(port.name, port.direction, port.data_type) for port in ports] == [
        ("image", PortDirection.INPUT, IMAGEJ),
        ("label", PortDirection.INPUT, STRING),
        ("processed", PortDirection.OUTPUT, IMAGEJ),
        ("title", PortDirection.OUTPUT, STRING),
    ]
    assert ADAPTERS.require("imagej-script") is IMAGEJ_SCRIPT


def test_file_node_infers_ports_from_selected_script(tmp_path: Path) -> None:
    script = tmp_path / "example.groovy"
    script.write_text("#@ String from_file\n#@output String result\n", encoding="utf-8")
    instance = IMAGEJ_SCRIPT_FILE.create_instance("script", parameters={"filename": str(script)})
    assert [port.name for port in IMAGEJ_SCRIPT_FILE.ports_for_instance(instance)] == [
        "filename",
        "from_file",
        "result",
    ]
    filename_port = IMAGEJ_SCRIPT_FILE.input_for_instance("filename", instance)
    assert filename_port is not None and filename_port.is_param and filename_port.data_type is FILE
    assert [param.name for param in IMAGEJ_SCRIPT_FILE.parameters] == ["filename"]
    assert [param.name for param in IMAGEJ_SCRIPT.parameters] == ["code"]
    assert ADAPTERS.require("imagej-script-file") is IMAGEJ_SCRIPT_FILE


def test_file_node_can_be_created_without_a_selected_file() -> None:
    instance = IMAGEJ_SCRIPT_FILE.create_instance("script")
    assert [port.name for port in IMAGEJ_SCRIPT_FILE.ports_for_instance(instance)] == ["filename"]
    with pytest.raises(ValueError, match="filename must not be empty"):
        IMAGEJ_SCRIPT_FILE.executor({}, instance.parameters)


def test_script_type_annotations_support_numeric_and_untyped_outputs() -> None:
    instance = IMAGEJ_SCRIPT.create_instance(
        "script",
        parameters={
            "code": "#@ Double (min=0, max=1) threshold\n"
            "#@output Integer count\n#@output metadata\n",
        },
    )
    ports = IMAGEJ_SCRIPT.ports_for_instance(instance)
    assert [port.name for port in ports] == ["threshold", "count", "metadata"]
    assert [port.data_type.id for port in ports] == ["float", "integer", "any"]


def test_invalid_script_source_and_duplicate_ports(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty"):
        IMAGEJ_SCRIPT.ports_for_instance(
            IMAGEJ_SCRIPT.create_instance("s", parameters={"code": ""})
        )
    with pytest.raises(ValueError, match="Duplicate"):
        IMAGEJ_SCRIPT.ports_for_instance(
            IMAGEJ_SCRIPT.create_instance(
                "s", parameters={"code": "#@ Dataset image\n#@output Dataset image"}
            )
        )
    with pytest.raises(FileNotFoundError):
        IMAGEJ_SCRIPT_FILE.ports_for_instance(
            IMAGEJ_SCRIPT_FILE.create_instance(
                "s", parameters={"filename": str(tmp_path / "no.groovy")}
            )
        )


def test_script_executes_with_converted_inputs_and_named_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = np.arange(6, dtype=np.uint8).reshape(2, 3)
    calls: list[tuple[str, str, dict[str, object]]] = []
    bridge = SimpleNamespace(
        to_dataset=lambda value: ("dataset", value),
        to_img=lambda value: ("img", value),
        to_java=lambda value: ("java", value),
        from_java=lambda value: value,
        run_script=lambda lang, source, args: (
            calls.append((lang, source, args)) or {"result": image, "title": "done"}
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "imagej",
        SimpleNamespace(
            init=lambda version, mode: (assert_init(version, mode), SimpleNamespace(py=bridge))[1]
        ),
    )
    source = NodeDefinition(
        id="image-source",
        icon="",
        label="Source",
        ports=(PortDefinition("image", PortDirection.OUTPUT, IMAGEJ),),
        executor=lambda _inputs, _parameters: {"image": image},
    )
    registry = NodeRegistry()
    registry.register(source)
    registry.register(IMAGEJ_SCRIPT)
    script = IMAGEJ_SCRIPT.create_instance(
        "script",
        parameters={
            "code": "#@ Dataset image\n#@output Dataset result\n#@output String title\nresult = image"
        },
    )
    graph = WorkflowGraph([source.create_instance("source"), script])
    graph.add_edge(WorkflowEdge("source", "image", "script", "image"), registry)

    result = WorkflowExecutor(registry).run(graph).node_outputs["script"]

    assert calls[0][0] == "Groovy"
    assert calls[0][2]["image"][0] == "dataset"
    assert calls[0][2]["image"][1] is image
    np.testing.assert_array_equal(result["result"], image)
    assert result["result"] is not image
    assert result["title"] == "done"


def assert_init(version: str, mode: str) -> None:
    assert version == "sc.fiji:fiji:2.14.0"
    assert mode == "headless"


def test_missing_declared_output_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = SimpleNamespace(run_script=lambda *_args: {}, to_java=lambda value: value)
    monkeypatch.setitem(
        sys.modules,
        "imagej",
        SimpleNamespace(init=lambda *_args, **_kw: SimpleNamespace(py=bridge)),
    )
    with pytest.raises(ValueError, match="did not produce output"):
        IMAGEJ_SCRIPT.executor({}, {"code": "#@output String result"})


def test_script_file_source_is_executed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    script = tmp_path / "source.groovy"
    script.write_text("#@output String result\nresult = 'file'", encoding="utf-8")
    calls: list[str] = []
    bridge = SimpleNamespace(
        run_script=lambda _language, source, _args: calls.append(source) or {"result": "file"},
        from_java=lambda value: value,
    )
    monkeypatch.setitem(
        sys.modules, "imagej", SimpleNamespace(init=lambda *_a, **_kw: SimpleNamespace(py=bridge))
    )
    assert IMAGEJ_SCRIPT_FILE.executor({}, {"filename": str(script)}) == {"result": "file"}
    assert calls == [script.read_text(encoding="utf-8")]


def test_file_node_filename_parameter_port_overrides_configured_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configured = tmp_path / "configured.groovy"
    configured.write_text("#@output String result\nresult = 'configured'", encoding="utf-8")
    selected = tmp_path / "selected.groovy"
    selected.write_text("#@output String result\nresult = 'selected'", encoding="utf-8")
    sources: list[str] = []
    bridge = SimpleNamespace(
        run_script=lambda _lang, source, _args: sources.append(source) or {"result": "selected"},
        from_java=lambda value: value,
    )
    monkeypatch.setitem(
        sys.modules, "imagej", SimpleNamespace(init=lambda *_a, **_kw: SimpleNamespace(py=bridge))
    )
    filename_source = NodeDefinition(
        id="filename-source",
        icon="",
        label="Filename",
        ports=(PortDefinition("filename", PortDirection.OUTPUT, FILE),),
        executor=lambda _inputs, _params: {"filename": FilePath(selected)},
    )
    registry = NodeRegistry()
    registry.register(filename_source)
    registry.register(IMAGEJ_SCRIPT_FILE)
    instance = IMAGEJ_SCRIPT_FILE.create_instance(
        "script", parameters={"filename": str(configured)}
    )
    graph = WorkflowGraph([filename_source.create_instance("source"), instance])
    graph.add_edge(WorkflowEdge("source", "filename", "script", "filename"), registry)

    assert WorkflowExecutor(registry).run(graph).node_outputs["script"]["result"] == "selected"
    assert sources == [selected.read_text(encoding="utf-8")]
    assert str(instance.parameters["filename"]) == str(selected)
