from pathlib import Path

import meshio
import numpy as np
import pytest
from Muscat.IO.XdmfReader import XdmfReader
from Muscat.MeshContainers.ElementsDescription import ElementType
from Muscat.TestData import GetTestDataPath

from flowgraph.adapters import ADAPTERS
from flowgraph.adapters.file_conversion import (
    MESH_FILE_CONVERSION,
    DelayInitialization,
    MeshFileConversionError,
)
from flowgraph.adapters.simple_sources import SET_BOOLEAN, SET_STRING
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import WorkflowEdge, WorkflowExecutor, WorkflowGraph
from flowgraph.domain.filepath import FilePath


def test_mesh_file_conversion_is_registered_in_mesh_tools_catalog() -> None:
    assert ADAPTERS.require("convert-mesh-file-format") is MESH_FILE_CONVERSION
    mesh_tools = next(group for group in ADAPTERS.groups if group.label == "Mesh Tools")
    conversion = next(group for group in mesh_tools.subgroups if group.label == "File Conversion")

    assert conversion.node_definitions == (MESH_FILE_CONVERSION,)


def test_mesh_file_conversion_exports_all_parameters_as_optional_inputs() -> None:
    assert [(port.name, port.direction.value) for port in MESH_FILE_CONVERSION.ports] == [
        ("converted_filename", "output"),
        ("input_filename", "input"),
        ("output_filename", "input"),
        ("reader", "input"),
        ("writer", "input"),
        ("timestep_to_read", "input"),
        ("binary", "input"),
    ]
    for parameter in MESH_FILE_CONVERSION.parameters:
        port = MESH_FILE_CONVERSION.input(parameter.name)
        assert port is not None and port.is_param and not port.required
        assert port.data_type is parameter.kind
    assert MESH_FILE_CONVERSION.default_parameters == {
        "input_filename": "",
        "output_filename": "",
        "reader": "auto",
        "writer": "auto",
        "timestep_to_read": "last",
        "binary": True,
    }


def test_delay_initialization_prefers_muscat_for_auto_extension() -> None:
    mapping = DelayInitialization(
        {
            ".mesh MeshIO Reader": "res = int",
            ".mesh Muscat Reader": "res = str",
        }
    )

    assert mapping.get_class("mesh.mesh", "auto") is str
    assert mapping.get_class("mesh.mesh", ".mesh MeshIO Reader") is int


def test_delay_initialization_rejects_unknown_auto_extension() -> None:
    mapping = DelayInitialization({".mesh Muscat Reader": "res = str"})

    with pytest.raises(MeshFileConversionError, match="No conversion class"):
        mapping.get_class("mesh.vtk", "auto")


def test_mesh_file_conversion_rejects_invalid_input_path(tmp_path: Path) -> None:
    with pytest.raises(MeshFileConversionError, match="does not exist"):
        MESH_FILE_CONVERSION.executor(
            {},
            {
                "input_filename": tmp_path / "missing.mesh",
                "output_filename": tmp_path / "output.vtk",
            },
        )


@pytest.mark.parametrize(
    ("reader", "writer"),
    [
        (".stl Muscat StlReader", ".meshb Muscat MeshWriter"),
        (".stl MeshIO stl_stl_Reader", ".meshb MeshIO meshb_medit_Writer"),
    ],
)
def test_mesh_file_conversion_converts_muscat_test_sphere_to_meshb(
    tmp_path: Path, reader: str, writer: str
) -> None:
    source = Path(GetTestDataPath()) / "stlsphere.stl"
    destination = tmp_path / f"stlsphere-{reader.split()[1].lower()}.meshb"

    values = {
        "input_filename": str(source),
        "output_filename": str(destination),
        "reader": reader,
        "writer": writer,
        "timestep_to_read": "first",
        "binary": False,
    }
    registry = create_node_registry()
    graph = WorkflowGraph([MESH_FILE_CONVERSION.create_instance("convert")])
    for name, value in values.items():
        definition = SET_BOOLEAN if isinstance(value, bool) else SET_STRING
        graph.add_node(definition.create_instance(name, parameters={"value": value}))
        graph.add_edge(WorkflowEdge(name, "value", "convert", name), registry)

    result = WorkflowExecutor(registry).run(graph)

    assert result.node_outputs["convert"] == {"converted_filename": FilePath(destination)}
    assert result.node_inputs["convert"] == {
        **values,
        "input_filename": FilePath(source),
        "output_filename": FilePath(destination),
    }
    assert destination.is_file()
    assert destination.stat().st_size > 0


@pytest.mark.parametrize("timestep", [None, "first", "all"], ids=["default-last", "first", "all"])
@pytest.mark.parametrize("output_extension", ["vtu", "xdmf"])
def test_mesh_file_conversion_writes_static_xdmf_as_one_mesh(
    tmp_path: Path, timestep: str | None, output_extension: str
) -> None:
    source = tmp_path / "static.xdmf"
    destination = tmp_path / f"converted.{output_extension}"
    points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 1.0]])
    triangles = np.array([[0, 1, 2]])
    temperature = np.array([1.0, 2.0, 3.0])
    pressure = np.array([4.0])
    meshio.write(
        source,
        meshio.Mesh(
            points,
            [("triangle", triangles)],
            point_data={"temperature": temperature},
            cell_data={"pressure": [pressure]} if output_extension == "xdmf" else None,
        ),
        data_format="XML",
    )
    parameters = {"input_filename": source, "output_filename": destination, "binary": False}
    if timestep is not None:
        parameters["timestep_to_read"] = timestep
    graph = WorkflowGraph([MESH_FILE_CONVERSION.create_instance("convert", parameters=parameters)])

    result = WorkflowExecutor(create_node_registry()).run(graph)

    assert result.node_outputs["convert"] == {"converted_filename": FilePath(destination)}
    if output_extension == "xdmf":
        reader = XdmfReader(destination)
        reader.ReadMetaData()
        assert len(reader.GetAvailableTimes()) == 0
        assert len(reader.xdmf.GetDomain(0).grids) == 1
        mesh = reader.Read()
        np.testing.assert_allclose(mesh.nodes, points)
        np.testing.assert_array_equal(mesh.elements[ElementType.Triangle_3].connectivity, triangles)
        np.testing.assert_allclose(mesh.nodeFields["temperature"].ravel(), temperature)
        np.testing.assert_allclose(mesh.elemFields["pressure"].ravel(), pressure)
    else:
        mesh = meshio.read(destination)
        np.testing.assert_allclose(mesh.points, points)
        np.testing.assert_array_equal(mesh.cells_dict["triangle"], triangles)
        np.testing.assert_allclose(mesh.point_data["temperature"].ravel(), temperature)


def test_mesh_file_conversion_writes_non_temporal_mesh_and_closes_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flowgraph.adapters import file_conversion

    source = tmp_path / "source.mesh"
    destination = tmp_path / "output.vtk"
    source.touch()
    calls: list[object] = []

    class Reader:
        canHandleTemporal = False

        def SetFileName(self, filename: Path) -> None:
            calls.append(("reader-file", filename))

        def Read(self) -> object:
            calls.append("read")
            return mesh

    class Writer:
        canHandleTemporal = False

        def SetFileName(self, filename: Path) -> None:
            calls.append(("writer-file", filename))

        def SetBinary(self, binary: bool) -> None:
            calls.append(("binary", binary))

        def Open(self) -> None:
            calls.append("open")

        def Write(self, value: object, **extras: object) -> None:
            calls.append(("write", value, extras))

        def Close(self) -> None:
            calls.append("close")

    mesh = type("Mesh", (), {"nodeFields": {}, "elemFields": {}})()
    monkeypatch.setattr(file_conversion, "ReaderMapping", _FixedMapping(Reader))
    monkeypatch.setattr(file_conversion, "WriterMapping", _FixedMapping(Writer))

    result = MESH_FILE_CONVERSION.executor(
        {},
        {"input_filename": source, "output_filename": destination},
    )

    assert result == {"converted_filename": FilePath(destination)}
    assert calls == [
        ("reader-file", source),
        "read",
        ("writer-file", destination),
        ("binary", True),
        "open",
        (
            "write",
            mesh,
            {
                "PointFieldsNames": [],
                "PointFields": [],
                "CellFieldsNames": [],
                "CellFields": [],
            },
        ),
        "close",
    ]


def test_mesh_file_conversion_closes_temporal_writer_after_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flowgraph.adapters import file_conversion

    source = tmp_path / "source.mesh"
    destination = tmp_path / "output.vtk"
    source.touch()
    calls: list[str] = []

    class Reader:
        canHandleTemporal = True

        def SetFileName(self, _filename: Path) -> None:
            pass

        def ReadMetaData(self) -> None:
            calls.append("metadata")

        def GetAvailableTimes(self) -> list[int]:
            return [10, 20]

        def SetTimeToRead(self, time: int) -> None:
            calls.append(f"time-{time}")

        def Read(self) -> object:
            return mesh

    class Writer:
        canHandleTemporal = True

        def SetFileName(self, _filename: Path) -> None:
            pass

        def SetBinary(self, _binary: bool) -> None:
            pass

        def SetTemporal(self) -> None:
            calls.append("temporal")

        def Open(self, _filename: Path) -> None:
            calls.append("open")

        def Write(self, _value: object, **_extras: object) -> None:
            calls.append("write")
            raise OSError("write failed")

        def Close(self) -> None:
            calls.append("close")

    mesh = type("Mesh", (), {"nodeFields": {}, "elemFields": {}})()
    monkeypatch.setattr(file_conversion, "ReaderMapping", _FixedMapping(Reader))
    monkeypatch.setattr(file_conversion, "WriterMapping", _FixedMapping(Writer))

    with pytest.raises(OSError, match="write failed"):
        MESH_FILE_CONVERSION.executor(
            {},
            {"timestep_to_read": "last", "input_filename": source, "output_filename": destination},
        )

    assert calls == ["metadata", "temporal", "open", "time-20", "write", "close"]


class _FixedMapping:
    def __init__(self, conversion_class: type[object]) -> None:
        self.conversion_class = conversion_class

    def GetClass(self, _filename: Path, _key: str) -> type[object]:
        return self.conversion_class
