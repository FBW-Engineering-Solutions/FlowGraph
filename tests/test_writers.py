import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from Muscat.MeshContainers.Mesh import Mesh

from flowgraph.adapters.readers import LOAD_MUSCAT
from flowgraph.adapters.writers import (
    WRITE_MESHIO,
    WRITE_MESHLANE,
    WRITE_MUSCAT,
    MeshWriteError,
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
