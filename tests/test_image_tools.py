from pathlib import Path

import numpy as np
import pytest
from Muscat.MeshContainers import ElementsDescription as ED
from Muscat.MeshContainers.ElementsContainers import StructuredElementsContainer
from PIL import Image as PillowImage

from flowgraph.adapters import ADAPTERS
from flowgraph.adapters.data_types import BOOLEAN, FILE, FLOAT, IMAGE, INTEGER
from flowgraph.adapters.image_tools import (
    AVAILABLE_NODES,
    CONVERT_IMAGE_MODE,
    CROP_IMAGE,
    IMAGE_TO_MESH,
    READ_IMAGE,
    RESIZE_IMAGE,
    ROTATE_IMAGE,
    WRITE_IMAGE,
    ImageLoadError,
    ImageOperationError,
    ImageWriteError,
)
from flowgraph.adapters.simple_sources import SET_FLOAT, SET_INT, SET_STRING
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import WorkflowEdge, WorkflowExecutor, WorkflowGraph


def test_image_data_type_accepts_pillow_images() -> None:
    assert IMAGE.accepts(PillowImage.new("RGB", (1, 1)))
    assert not IMAGE.accepts("not an image")


def test_image_tools_are_registered_in_a_top_level_group() -> None:
    group = next(group for group in ADAPTERS.groups if group.label == "Image Tools")

    assert group.node_definitions == AVAILABLE_NODES
    assert [definition.id for definition in group.node_definitions] == [
        "read-image",
        "write-image",
        "resize-image",
        "crop-image",
        "rotate-image",
        "convert-image-mode",
        "image-to-mesh",
    ]


def test_image_operation_parameters_are_exported_parameter_ports() -> None:
    read_path = READ_IMAGE.input("path")
    write_filename = WRITE_IMAGE.input("filename")
    resize_width = RESIZE_IMAGE.input("width")
    resize_height = RESIZE_IMAGE.input("height")
    crop_coordinates = tuple(CROP_IMAGE.input(name) for name in ("left", "top", "right", "bottom"))
    rotate_angle = ROTATE_IMAGE.input("angle")

    assert read_path is not None and read_path.is_param and read_path.data_type is FILE
    assert (
        write_filename is not None and write_filename.is_param and write_filename.data_type is FILE
    )
    assert resize_width is not None and resize_width.is_param and resize_width.data_type is INTEGER
    assert (
        resize_height is not None and resize_height.is_param and resize_height.data_type is INTEGER
    )
    assert all(
        coordinate is not None and coordinate.is_param and coordinate.data_type is INTEGER
        for coordinate in crop_coordinates
    )
    assert rotate_angle is not None and rotate_angle.is_param and rotate_angle.data_type is FLOAT

    assert READ_IMAGE.parameters[0].kind is FILE
    assert WRITE_IMAGE.parameters[0].kind is FILE
    assert RESIZE_IMAGE.parameters[0].kind is INTEGER
    assert RESIZE_IMAGE.parameters[1].kind is INTEGER
    assert all(parameter.kind is INTEGER for parameter in CROP_IMAGE.parameters)
    assert ROTATE_IMAGE.parameters[0].kind is FLOAT
    assert ROTATE_IMAGE.parameters[1].kind is BOOLEAN


def test_read_image_loads_a_detached_pillow_image(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    PillowImage.new("RGB", (3, 2), (12, 34, 56)).save(source)

    image = READ_IMAGE.executor({}, {"path": source})["image"]

    assert isinstance(image, PillowImage.Image)
    assert image.mode == "RGB"
    assert image.size == (3, 2)
    assert image.getpixel((0, 0)) == (12, 34, 56)


def test_read_image_rejects_missing_source(tmp_path: Path) -> None:
    with pytest.raises(ImageLoadError, match="does not exist"):
        READ_IMAGE.executor({}, {"path": tmp_path / "missing.png"})


def test_write_image_writes_a_pillow_image(tmp_path: Path) -> None:
    destination = tmp_path / "written.png"
    source = PillowImage.new("RGBA", (2, 4), (1, 2, 3, 4))

    outputs = WRITE_IMAGE.executor({"image": source}, {"filename": destination})

    assert outputs == {}
    with PillowImage.open(destination) as written:
        assert written.mode == "RGBA"
        assert written.size == (2, 4)
        assert written.getpixel((0, 0)) == (1, 2, 3, 4)


def test_write_image_rejects_extensionless_destination(tmp_path: Path) -> None:
    with pytest.raises(ImageWriteError, match="no extension"):
        WRITE_IMAGE.executor(
            {"image": PillowImage.new("RGB", (1, 1))},
            {"filename": tmp_path / "image"},
        )


def test_resize_image_returns_a_resized_copy_without_mutating_the_source() -> None:
    source = PillowImage.new("RGB", (4, 2), (12, 34, 56))

    result = RESIZE_IMAGE.executor({"image": source}, {"width": 2, "height": 1})["image"]

    assert result is not source
    assert source.size == (4, 2)
    assert result.size == (2, 1)
    assert result.mode == "RGB"


@pytest.mark.parametrize("parameters", [{"width": 0, "height": 1}, {"width": 1, "height": True}])
def test_resize_image_rejects_non_positive_or_non_integer_dimensions(
    parameters: dict[str, int | bool],
) -> None:
    with pytest.raises(ImageOperationError, match="positive integer"):
        RESIZE_IMAGE.executor({"image": PillowImage.new("RGB", (1, 1))}, parameters)


def test_resize_parameter_ports_override_configured_dimensions_in_a_workflow(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    PillowImage.new("RGB", (6, 4), (12, 34, 56)).save(source)
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            READ_IMAGE.create_instance("read", parameters={"path": str(source)}),
            SET_INT.create_instance("width", parameters={"value": 3}),
            SET_INT.create_instance("height", parameters={"value": 2}),
            RESIZE_IMAGE.create_instance("resize", parameters={"width": 99, "height": 99}),
        ]
    )
    graph.add_edge(WorkflowEdge("read", "image", "resize", "image"), registry)
    graph.add_edge(WorkflowEdge("width", "value", "resize", "width"), registry)
    graph.add_edge(WorkflowEdge("height", "value", "resize", "height"), registry)

    result = WorkflowExecutor(registry).run(graph)

    assert result.node_outputs["resize"]["image"].size == (3, 2)
    assert result.node_inputs["resize"]["width"] == 3
    assert result.node_inputs["resize"]["height"] == 2


def test_crop_parameter_ports_override_configured_coordinates_in_a_workflow(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    PillowImage.new("RGB", (6, 4), (12, 34, 56)).save(source)
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            READ_IMAGE.create_instance("read", parameters={"path": str(source)}),
            SET_INT.create_instance("right", parameters={"value": 3}),
            SET_INT.create_instance("bottom", parameters={"value": 2}),
            CROP_IMAGE.create_instance(
                "crop", parameters={"left": 0, "top": 0, "right": 6, "bottom": 4}
            ),
        ]
    )
    graph.add_edge(WorkflowEdge("read", "image", "crop", "image"), registry)
    graph.add_edge(WorkflowEdge("right", "value", "crop", "right"), registry)
    graph.add_edge(WorkflowEdge("bottom", "value", "crop", "bottom"), registry)

    result = WorkflowExecutor(registry).run(graph)

    assert result.node_outputs["crop"]["image"].size == (3, 2)
    assert result.node_inputs["crop"]["right"] == 3
    assert result.node_inputs["crop"]["bottom"] == 2


def test_crop_image_returns_the_selected_in_bounds_region() -> None:
    source = PillowImage.fromarray(np.arange(20, dtype=np.uint8).reshape(4, 5), mode="L")

    result = CROP_IMAGE.executor({"image": source}, {"left": 1, "top": 1, "right": 4, "bottom": 3})[
        "image"
    ]

    assert source.size == (5, 4)
    assert result.size == (3, 2)
    np.testing.assert_array_equal(np.asarray(result), [[6, 7, 8], [11, 12, 13]])


@pytest.mark.parametrize(
    "parameters, message",
    [
        ({"left": 2, "top": 0, "right": 2, "bottom": 1}, "must exceed"),
        ({"left": 0, "top": 0, "right": 3, "bottom": 1}, "exceeds image bounds"),
    ],
)
def test_crop_image_rejects_invalid_crop_boxes(parameters: dict[str, int], message: str) -> None:
    with pytest.raises(ImageOperationError, match=message):
        CROP_IMAGE.executor({"image": PillowImage.new("RGB", (2, 2))}, parameters)


def test_rotate_image_rotates_counter_clockwise_and_expands_output() -> None:
    source = PillowImage.new("RGB", (3, 1), (12, 34, 56))

    result = ROTATE_IMAGE.executor({"image": source}, {"angle": 90, "expand": True})["image"]

    assert source.size == (3, 1)
    assert result.size == (1, 3)
    assert result.getpixel((0, 1)) == (12, 34, 56)


def test_rotate_angle_parameter_port_overrides_the_configured_angle_in_a_workflow(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    PillowImage.new("RGB", (3, 1), (12, 34, 56)).save(source)
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            READ_IMAGE.create_instance("read", parameters={"path": str(source)}),
            SET_FLOAT.create_instance("angle", parameters={"value": 90.0}),
            ROTATE_IMAGE.create_instance("rotate", parameters={"angle": 0.0, "expand": True}),
        ]
    )
    graph.add_edge(WorkflowEdge("read", "image", "rotate", "image"), registry)
    graph.add_edge(WorkflowEdge("angle", "value", "rotate", "angle"), registry)

    result = WorkflowExecutor(registry).run(graph)

    assert result.node_outputs["rotate"]["image"].size == (1, 3)
    assert result.node_inputs["rotate"]["angle"] == 90.0


def test_convert_image_mode_converts_to_the_selected_color_mode() -> None:
    source = PillowImage.new("RGBA", (1, 1), (12, 34, 56, 78))

    result = CONVERT_IMAGE_MODE.executor({"image": source}, {"mode": "L"})["image"]

    assert source.mode == "RGBA"
    assert result.mode == "L"
    assert result.size == source.size


def test_convert_image_mode_rejects_an_unsupported_mode() -> None:
    with pytest.raises(ImageOperationError, match="Unsupported target color mode"):
        CONVERT_IMAGE_MODE.executor({"image": PillowImage.new("RGB", (1, 1))}, {"mode": "XYZ"})


def test_image_nodes_round_trip_through_png(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    destination = tmp_path / "destination.png"
    PillowImage.new("L", (2, 2), 128).save(source)

    image = READ_IMAGE.executor({}, {"path": source})["image"]
    WRITE_IMAGE.executor({"image": image}, {"filename": destination})

    with PillowImage.open(destination) as result:
        assert result.mode == "L"
        assert result.size == (2, 2)
        assert result.getpixel((0, 0)) == 128


@pytest.mark.parametrize(
    ("mode", "color", "components"),
    [
        ("L", 12, 1),
        ("LA", (12, 34), 2),
        ("RGB", (12, 34, 56), 3),
        ("RGBA", (12, 34, 56, 78), 4),
    ],
)
def test_image_to_mesh_creates_structured_node_colors(
    mode: str, color: int | tuple[int, ...], components: int
) -> None:
    image = PillowImage.new(mode, (3, 2), color)

    document = IMAGE_TO_MESH.executor({"image": image}, {"storeOnNodeFields": True})["mesh"]
    mesh = document.mesh
    colors = mesh.nodeFields["Colors"]

    assert mesh.GetNumberOfNodes() == 6
    assert mesh.GetNumberOfElements() == 2
    assert isinstance(mesh.elements[ED.Quadrangle_4], StructuredElementsContainer)
    assert colors.shape == (mesh.GetNumberOfNodes(), components)
    np.testing.assert_array_equal(colors, np.tile(np.asarray(color).reshape(1, -1), (6, 1)))
    assert "Colors" not in mesh.elemFields


def test_image_to_mesh_uses_muscat_node_order_for_pixel_colors() -> None:
    image = PillowImage.fromarray(np.array([[1, 2, 3], [4, 5, 6]], dtype=np.uint8), mode="L")

    document = IMAGE_TO_MESH.executor({"image": image}, {})["mesh"]

    np.testing.assert_array_equal(
        document.mesh.nodeFields["Colors"], np.array([[1], [4], [2], [5], [3], [6]])
    )


def test_image_to_mesh_stores_one_color_per_element() -> None:
    image = PillowImage.fromarray(np.array([[0, 2, 4], [6, 8, 10]], dtype=np.uint8), mode="L")

    document = IMAGE_TO_MESH.executor({"image": image}, {"storeOnNodeFields": False})["mesh"]
    mesh = document.mesh

    assert "Colors" not in mesh.nodeFields
    assert mesh.elemFields["Colors"].shape == (mesh.GetNumberOfElements(), 1)
    np.testing.assert_array_equal(mesh.elemFields["Colors"], [[0], [6], [2], [8], [4], [10]])


def test_read_image_connects_to_image_to_mesh_in_a_workflow(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    PillowImage.new("RGB", (3, 2), (9, 8, 7)).save(source)
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            SET_STRING.create_instance("source-path", parameters={"value": str(source)}),
            READ_IMAGE.create_instance("read", parameters={"path": "unused.png"}),
            IMAGE_TO_MESH.create_instance("convert"),
        ]
    )
    graph.add_edge(WorkflowEdge("source-path", "value", "read", "path"), registry)
    graph.add_edge(WorkflowEdge("read", "image", "convert", "image"), registry)

    result = WorkflowExecutor(registry).run(graph)
    mesh = result.node_outputs["convert"]["mesh"].mesh

    assert mesh.nodeFields["Colors"].shape == (6, 3)
    np.testing.assert_array_equal(mesh.nodeFields["Colors"], np.tile([[9, 8, 7]], (6, 1)))


def test_image_file_parameter_ports_override_configured_paths(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    destination = tmp_path / "destination.png"
    PillowImage.new("RGB", (1, 1), (9, 8, 7)).save(source)
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            SET_STRING.create_instance("source-path", parameters={"value": str(source)}),
            SET_STRING.create_instance("destination-path", parameters={"value": str(destination)}),
            READ_IMAGE.create_instance("read", parameters={"path": "unused.png"}),
            WRITE_IMAGE.create_instance("write", parameters={"filename": "unused.png"}),
        ]
    )
    graph.add_edge(WorkflowEdge("source-path", "value", "read", "path"), registry)
    graph.add_edge(WorkflowEdge("read", "image", "write", "image"), registry)
    graph.add_edge(WorkflowEdge("destination-path", "value", "write", "filename"), registry)

    result = WorkflowExecutor(registry).run(graph)

    assert destination.is_file()
    assert result.node_inputs["read"] == {"path": str(source)}
    assert result.node_inputs["write"] == {
        "image": result.node_outputs["read"]["image"],
        "filename": str(destination),
    }
