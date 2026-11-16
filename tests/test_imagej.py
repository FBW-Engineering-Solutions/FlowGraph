"""Tests for script-derived ImageJ ports and the optional PyImageJ bridge."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from flowgraph.adapters import ADAPTERS
from flowgraph.adapters.data_types import FILE, IMAGEJ, STRING
from flowgraph.adapters.imagej import (
    IMAGEJ_SCRIPT,
    IMAGEJ_SCRIPT_FILE,
    _from_imageplus,
    _to_imageplus,
)
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


@pytest.mark.parametrize("definition", [IMAGEJ_SCRIPT, IMAGEJ_SCRIPT_FILE])
@pytest.mark.parametrize("typename", ["ImagePlus", "ij.ImagePlus"])
def test_imageplus_ports_are_typed(definition, typename, tmp_path) -> None:
    code = f"#@ {typename} imp\n#@output {typename} result\nresult = imp"
    script = tmp_path / "imageplus.groovy"
    script.write_text(code, encoding="utf-8")
    instance = definition.create_instance(
        "script", parameters={"code": code, "filename": str(script)}
    )
    assert [
        (port.name, port.data_type)
        for port in definition.ports_for_instance(instance)
        if not port.is_param
    ] == [("imp", IMAGEJ), ("result", IMAGEJ)]


@pytest.mark.parametrize(
    ("dtype", "shape", "processor_type", "image_type"),
    [
        (np.uint8, (3, 5), "ByteProcessor", 0),
        (np.uint16, (3, 5), "ShortProcessor", 1),
        (np.float32, (3, 5), "FloatProcessor", 2),
        (np.uint8, (3, 5, 3), "ColorProcessor", 4),
    ],
)
def test_imageplus_processor_round_trip(monkeypatch, dtype, shape, processor_type, image_type):
    array = (np.arange(np.prod(shape)).reshape(shape) * 500).astype(dtype)
    calls = []

    def processor(width, height, pixels, *_args):
        calls.append((width, height))
        return SimpleNamespace(getPixels=lambda: pixels)

    def imageplus(_title, proc):
        return SimpleNamespace(
            getStackSize=lambda: 1,
            getHeight=lambda: shape[0],
            getWidth=lambda: shape[1],
            getType=lambda: image_type,
            getProcessor=lambda: proc,
        )

    monkeypatch.setitem(
        sys.modules,
        "jpype",
        SimpleNamespace(
            JByte=np.int8,
            JShort=np.int16,
            JFloat=np.float32,
            JInt=np.int32,
            JArray=lambda dtype: lambda pixels: np.array(pixels, dtype=dtype, copy=True),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "scyjava",
        SimpleNamespace(
            jimport=lambda name: (
                imageplus
                if name == "ij.ImagePlus"
                else processor
                if name == f"ij.process.{processor_type}"
                else pytest.fail(name)
            )
        ),
    )
    original = array.copy()
    image = _to_imageplus(array[:, ::-1])
    output = _from_imageplus(image)
    assert calls == [(shape[1], shape[0])]
    assert output.dtype == dtype
    np.testing.assert_array_equal(output, array[:, ::-1])
    image.getProcessor().getPixels()[0] = 0
    np.testing.assert_array_equal(array, original)
    assert not np.shares_memory(output, image.getProcessor().getPixels())


@pytest.mark.parametrize(
    "array",
    [
        np.zeros((2, 3, 4), dtype=np.uint8),
        np.zeros((2, 3, 2), dtype=np.uint8),
        np.zeros((2, 3), dtype=np.float64),
        np.zeros((0, 3), dtype=np.uint8),
        np.zeros((2, 3, 3), dtype=np.uint16),
        np.zeros((2, 3, 4, 5), dtype=np.uint8),
    ],
)
def test_imageplus_rejects_unsupported_inputs(array):
    with pytest.raises(ValueError, match="ImagePlus"):
        _to_imageplus(array)


def test_imageplus_outputs_reject_stacks_and_indexed_color():
    with pytest.raises(ValueError, match="stack"):
        _from_imageplus(SimpleNamespace(getStackSize=lambda: 2))
    with pytest.raises(ValueError, match="indexed color"):
        _from_imageplus(
            SimpleNamespace(
                getStackSize=lambda: 1,
                getHeight=lambda: 2,
                getWidth=lambda: 3,
                getType=lambda: 3,
                getProcessor=lambda: SimpleNamespace(getPixels=lambda: np.zeros(6, dtype=np.int8)),
            )
        )


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


@pytest.mark.parametrize("explicit_conversion", [False, True])
@pytest.mark.parametrize("definition", [IMAGEJ_SCRIPT, IMAGEJ_SCRIPT_FILE])
def test_pillow_to_imageplus_script_to_pillow_workflow(
    monkeypatch, tmp_path, explicit_conversion, definition
):
    from PIL import Image

    from flowgraph.adapters import imagej as adapter
    from flowgraph.adapters.image_tools import IMAGEJ_TO_PILLOW, PILLOW_TO_IMAGEJ, READ_IMAGE
    from flowgraph.application.node_registry import create_node_registry

    pixels = np.arange(45, dtype=np.uint8).reshape(3, 5, 3)
    path = tmp_path / "image.png"
    Image.fromarray(pixels).save(path)
    code = "#@ ImagePlus imp\n#@output ImagePlus result\nresult = imp"
    script = tmp_path / "script.groovy"
    script.write_text(code, encoding="utf-8")
    monkeypatch.setattr(adapter, "_to_imageplus", lambda value: ("imageplus", value.copy()))
    monkeypatch.setattr(adapter, "_from_imageplus", lambda value: value[1].copy())

    def run_script(_language, _source, args):
        assert "#@ ij.ImagePlus imp" in _source
        assert "#@output ij.ImagePlus result" in _source
        assert args["imp"][0] == "imageplus"
        args["imp"][1][0, 0] = 0
        return {"result": args["imp"]}

    monkeypatch.setitem(
        sys.modules,
        "imagej",
        SimpleNamespace(
            init=lambda *_a, **_kw: SimpleNamespace(py=SimpleNamespace(run_script=run_script))
        ),
    )
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            READ_IMAGE.create_instance("read", parameters={"path": str(path)}),
            definition.create_instance(
                "script", parameters={"code": code, "filename": str(script)}
            ),
            IMAGEJ_TO_PILLOW.create_instance("pillow"),
        ]
    )
    source = "read"
    if explicit_conversion:
        graph.add_node(PILLOW_TO_IMAGEJ.create_instance("numpy"))
        graph.add_edge(WorkflowEdge("read", "image", "numpy", "image"), registry)
        source = "numpy"
    graph.add_edge(WorkflowEdge(source, "image", "script", "imp"), registry)
    graph.add_edge(WorkflowEdge("script", "result", "pillow", "image"), registry)

    result = WorkflowExecutor(registry).run(graph)

    expected = pixels.copy()
    expected[0, 0] = 0
    np.testing.assert_array_equal(np.asarray(result.node_outputs["pillow"]["image"]), expected)
    np.testing.assert_array_equal(np.asarray(result.node_outputs["read"]["image"]), pixels)


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


@pytest.mark.parametrize("definition", [IMAGEJ_SCRIPT, IMAGEJ_SCRIPT_FILE])
@pytest.mark.parametrize("qualifier", ["", "input ", "output "])
@pytest.mark.parametrize("spacing", ["", " ", "\t"])
def test_parameter_metadata_can_immediately_follow_type(
    definition: NodeDefinition, qualifier: str, spacing: str, tmp_path: Path
) -> None:
    source = f'#@ {qualifier}Integer{spacing}(label="Gaussian Sigma", min=1, max=10, value=2) sigma'
    if definition is IMAGEJ_SCRIPT_FILE:
        script = tmp_path / "gaussian.groovy"
        script.write_text(source, encoding="utf-8")
        parameters = {"filename": str(script)}
    else:
        parameters = {"code": source}
    instance = definition.create_instance("script", parameters=parameters)
    ports = [port for port in definition.ports_for_instance(instance) if not port.is_param]
    direction = PortDirection.OUTPUT if qualifier == "output " else PortDirection.INPUT
    assert [(port.name, port.direction, port.data_type.id) for port in ports] == [
        ("sigma", direction, "integer"),
    ]


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


def assert_init(version: list[str], mode: str) -> None:
    assert version == [
        "sc.fiji:fiji:2.18.0",
        "org.scala-lang:scala-library:2.13.10",
        "org.openjdk.nashorn:nashorn-core:15.7",
    ]
    assert mode == "headless"


@pytest.mark.parametrize("already_started", [False, True])
def test_imagej_selects_java_21_before_initialization(
    monkeypatch: pytest.MonkeyPatch, already_started: bool
) -> None:
    calls: list[tuple[object, ...]] = []
    monkeypatch.setitem(
        sys.modules,
        "scyjava",
        SimpleNamespace(
            jvm_started=lambda: already_started,
            config=SimpleNamespace(
                set_java_constraints=lambda **kwargs: calls.append(("constraints", kwargs))
            ),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "imagej",
        SimpleNamespace(
            init=lambda version, mode: (
                calls.append(("init", version, mode)),
                SimpleNamespace(
                    py=SimpleNamespace(
                        run_script=lambda *_args: {"status": "ok"}, from_java=lambda value: value
                    )
                ),
            )[1]
        ),
    )

    assert IMAGEJ_SCRIPT.executor({}, {"code": "#@output String status\nstatus = 'ok'"}) == {
        "status": "ok"
    }
    assert calls == (
        [("constraints", {"fetch": "auto", "version": "21"})] if not already_started else []
    ) + [
        (
            "init",
            [
                "sc.fiji:fiji:2.18.0",
                "org.scala-lang:scala-library:2.13.10",
                "org.openjdk.nashorn:nashorn-core:15.7",
            ],
            "headless",
        )
    ]


@pytest.mark.parametrize("definition", [IMAGEJ_SCRIPT, IMAGEJ_SCRIPT_FILE])
@pytest.mark.parametrize("image_type", ["Dataset", "ImagePlus"])
def test_null_image_output_is_reported_at_script_node(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, definition: NodeDefinition, image_type: str
) -> None:
    bridge = SimpleNamespace(
        run_script=lambda *_args: {"result": None}, from_java=lambda value: value
    )
    monkeypatch.setitem(
        sys.modules,
        "imagej",
        SimpleNamespace(init=lambda *_args, **_kw: SimpleNamespace(py=bridge)),
    )
    source = f"#@output {image_type} result"
    script = tmp_path / "null.groovy"
    script.write_text(source, encoding="utf-8")
    parameters = {"code": source, "filename": str(script)}

    with pytest.raises(ValueError, match="output 'result' is null.*ImagePlus, not a Dataset"):
        definition.executor({}, parameters)


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
