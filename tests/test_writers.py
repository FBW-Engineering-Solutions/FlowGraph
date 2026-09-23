import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest
from Muscat.MeshContainers.Mesh import Mesh

from flowgraph.adapters.data_types import TABLE_DOCUMENT
from flowgraph.adapters.readers import LOAD_MUSCAT
from flowgraph.adapters.writers import (
    WRITE_MESHIO,
    WRITE_MESHLANE,
    WRITE_MUSCAT,
    WRITE_TABLE,
    MeshWriteError,
    TableWriteError,
)
from flowgraph.domain.mesh_document import MeshDocument


def test_write_muscat_rejects_extensionless_filename(tmp_path: Path) -> None:
    document = MeshDocument(mesh=Mesh())

    with pytest.raises(MeshWriteError, match="no extension"):
        WRITE_MUSCAT.executor({"path": str(tmp_path / "mesh"), "mesh": document}, {})


def test_write_muscat_rejects_missing_output_directory(tmp_path: Path) -> None:
    document = MeshDocument(mesh=Mesh())

    with pytest.raises(MeshWriteError, match="output directory does not exist"):
        WRITE_MUSCAT.executor(
            {"path": str(tmp_path / "missing" / "mesh.mesh"), "mesh": document},
            {},
        )


def test_write_muscat_writes_mesh(tmp_path: Path) -> None:
    from Muscat.TestData import GetTestDataPath

    source = Path(GetTestDataPath()) / "square2D.mesh"
    document = LOAD_MUSCAT.executor({"path": str(source)}, {})["mesh"]
    destination = tmp_path / "written.mesh"

    outputs = WRITE_MUSCAT.executor({"path": str(destination), "mesh": document}, {})

    assert outputs == {}
    assert destination.is_file()


def test_write_muscat_uses_configured_path_parameter_when_unconnected(tmp_path: Path) -> None:
    from Muscat.TestData import GetTestDataPath

    source = Path(GetTestDataPath()) / "square2D.mesh"
    document = LOAD_MUSCAT.executor({"path": str(source)}, {})["mesh"]
    destination = tmp_path / "configured.mesh"

    outputs = WRITE_MUSCAT.executor({"mesh": document}, {"path": destination})

    assert outputs == {}
    assert destination.is_file()


def test_write_meshio_rejects_extensionless_filename(tmp_path: Path) -> None:
    document = MeshDocument(mesh=Mesh())

    with pytest.raises(MeshWriteError, match="no extension"):
        WRITE_MESHIO.executor({"path": str(tmp_path / "mesh"), "mesh": document}, {})


def test_write_meshio_rejects_missing_output_directory(tmp_path: Path) -> None:
    document = MeshDocument(mesh=Mesh())

    with pytest.raises(MeshWriteError, match="output directory does not exist"):
        WRITE_MESHIO.executor(
            {"path": str(tmp_path / "missing" / "mesh.vtk"), "mesh": document},
            {},
        )


def test_write_meshio_delegates_conversion_to_muscat_bridge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mesh = Mesh()
    document = MeshDocument(mesh=mesh)
    destination = tmp_path / "written.vtk"
    converted_mesh = object()
    calls = []

    def convert(source: Mesh) -> object:
        assert source is mesh
        return converted_mesh

    def write(filename: Path, output_mesh: object) -> None:
        calls.append((filename, output_mesh))

    monkeypatch.setattr("Muscat.Bridges.MeshIOBridge.MeshToMeshIO", convert)
    monkeypatch.setattr("meshio.write", write)

    outputs = WRITE_MESHIO.executor({"path": destination, "mesh": document}, {})

    assert outputs == {}
    assert calls == [(destination, converted_mesh)]


def test_write_meshlane_delegates_conversion_to_muscat_bridge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mesh = Mesh()
    document = MeshDocument(mesh=mesh)
    destination = tmp_path / "written.vtk"
    converted_mesh = object()
    write_calls = []

    def convert(source: Mesh) -> object:
        assert source is mesh
        return converted_mesh

    def write(filename: Path, output_mesh: object) -> None:
        write_calls.append((filename, output_mesh))

    bridge = ModuleType("Muscat.Bridges.MeshlaneBridge")
    bridge.MeshToMeshlane = convert  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "Muscat.Bridges.MeshlaneBridge", bridge)
    monkeypatch.setitem(
        sys.modules,
        "meshlane",
        SimpleNamespace(write=write),
    )

    outputs = WRITE_MESHLANE.executor({"path": destination, "mesh": document}, {})

    assert outputs == {}
    assert write_calls == [(destination, converted_mesh)]


def test_write_table_writes_an_excel_workbook(tmp_path: Path) -> None:
    destination = tmp_path / "output.xlsx"
    data = {"name": ["Ada", "Grace"], "age": [36, 28]}

    outputs = WRITE_TABLE.executor(
        {"data": data},
        {"path": destination, "sheet_name": "Employees", "header": True},
    )

    assert outputs == {}
    written = pd.read_excel(destination, sheet_name="Employees")
    assert list(written.columns) == ["name", "age"]
    assert written.to_dict(orient="list") == data


def test_write_table_uses_default_sheet_name_and_can_omit_headers(tmp_path: Path) -> None:
    destination = tmp_path / "output.xlsx"

    WRITE_TABLE.executor(
        {"data": {"name": ["Ada"], "age": [36]}},
        {"path": destination, "header": False},
    )

    written = pd.read_excel(destination, header=None)
    assert written.to_dict(orient="records") == [{0: "Ada", 1: 36}]


def test_write_table_exposes_requested_parameters_and_registers() -> None:
    from flowgraph.adapters import ADAPTERS

    assert ADAPTERS.require("write-table") is WRITE_TABLE
    assert WRITE_TABLE.input("data").data_type is TABLE_DOCUMENT
    assert WRITE_TABLE.input("path").is_param
    assert WRITE_TABLE.input("sheet_name").is_param
    assert WRITE_TABLE.input("header") is None
    assert [(parameter.name, parameter.default, parameter.port) for parameter in WRITE_TABLE.parameters] == [
        ("path", "output_pandas.xlsx", True),
        ("sheet_name", "", True),
        ("header", True, False),
    ]


def test_write_table_rejects_missing_output_directory(tmp_path: Path) -> None:
    with pytest.raises(TableWriteError, match="output directory does not exist"):
        WRITE_TABLE.executor(
            {"data": {"name": ["Ada"]}},
            {"path": tmp_path / "missing" / "output.xlsx"},
        )
