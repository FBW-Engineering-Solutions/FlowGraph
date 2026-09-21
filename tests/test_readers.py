import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import meshio
import pytest

from flowgraph.adapters import ADAPTERS
from flowgraph.adapters.data_types import LIST_STR, STRING
from flowgraph.adapters.files import READ_DIRECTORY_FILES, DirectoryReadError
from flowgraph.adapters.readers import (
    LOAD_MESHIO,
    LOAD_MESHLANE,
)
from flowgraph.domain.mesh_document import MeshDocument


def test_load_meshio_converts_mesh_through_muscat_bridge(tmp_path: Path) -> None:
    source = tmp_path / "triangle.vtk"
    meshio.write(
        source,
        meshio.Mesh(
            points=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            cells=[("triangle", [[0, 1, 2]])],
        ),
    )

    document = LOAD_MESHIO.executor({"path": source}, {})["mesh"]

    assert isinstance(document, MeshDocument)
    assert document.mesh.GetNumberOfNodes() == 3
    assert document.mesh.GetNumberOfElements() == 1


def test_load_meshio_uses_configured_path_parameter_when_unconnected(tmp_path: Path) -> None:
    source = tmp_path / "triangle.vtk"
    meshio.write(
        source,
        meshio.Mesh(
            points=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            cells=[("triangle", [[0, 1, 2]])],
        ),
    )

    document = LOAD_MESHIO.executor({}, {"path": source})["mesh"]

    assert isinstance(document, MeshDocument)
    assert document.mesh.GetNumberOfNodes() == 3


def test_load_meshlane_converts_mesh_through_muscat_bridge(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "triangle.vtk"
    source.touch()
    meshlane_mesh = object()
    converted_mesh = SimpleNamespace(
        GetNumberOfNodes=lambda: 3,
        GetNumberOfElements=lambda: 1,
    )
    calls: list[tuple[str, object]] = []

    def read(filename: Path) -> object:
        calls.append(("read", filename))
        return meshlane_mesh

    def convert(source_mesh: object) -> object:
        calls.append(("convert", source_mesh))
        return converted_mesh

    bridge = ModuleType("Muscat.Bridges.MeshlaneBridge")
    bridge.MeshlaneToMesh = convert  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "meshlane", SimpleNamespace(read=read))
    monkeypatch.setitem(sys.modules, "Muscat.Bridges.MeshlaneBridge", bridge)
    monkeypatch.setattr(
        "flowgraph.adapters.readers.MeshDocument",
        lambda mesh: SimpleNamespace(mesh=mesh),
    )

    document = LOAD_MESHLANE.executor({"path": source}, {})["mesh"]

    assert calls == [("read", source), ("convert", meshlane_mesh)]
    assert document.mesh is converted_mesh


def test_read_directory_files_lists_sorted_immediate_file_names(tmp_path: Path) -> None:
    (tmp_path / "zeta.txt").touch()
    (tmp_path / "alpha.csv").touch()
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "child.csv").touch()

    result = READ_DIRECTORY_FILES.executor({"path": tmp_path}, {})

    assert result == {"files": ["alpha.csv", "zeta.txt"]}


def test_read_directory_files_filters_with_inclusive_and_exclusive_regexes(tmp_path: Path) -> None:
    for filename in ("data.csv", "report.txt", "report.generated.csv", "image.png"):
        (tmp_path / filename).touch()

    result = READ_DIRECTORY_FILES.executor(
        {"path": tmp_path},
        {"patterns": "# Include text and CSV files\ninclude:\\.(csv|txt)$\nexclude:generated"},
    )

    assert result == {"files": ["data.csv", "report.txt"]}


def test_read_directory_files_rejects_invalid_pattern_rules(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="line 1"):
        READ_DIRECTORY_FILES.executor({"path": tmp_path}, {"patterns": "["})


def test_read_directory_files_rejects_a_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(DirectoryReadError, match="does not exist or is not a directory"):
        READ_DIRECTORY_FILES.executor({"path": tmp_path / "missing"}, {})


def test_read_directory_files_is_registered_with_text_path_and_list_text_output() -> None:
    assert ADAPTERS.require("read-directory-files") is READ_DIRECTORY_FILES
    assert [(port.name, port.data_type) for port in READ_DIRECTORY_FILES.inputs] == [
        ("path", STRING)
    ]
    assert [(port.name, port.data_type) for port in READ_DIRECTORY_FILES.outputs] == [
        ("files", LIST_STR)
    ]
    assert READ_DIRECTORY_FILES.parameters[0].port is False
