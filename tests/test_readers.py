import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import meshio
import numpy as np
import pytest
from Muscat.IO.XdmfWriter import XdmfWriter
from Muscat.MeshTools.MeshCreationTools import CreateMeshOfTriangles
from Muscat.TestData import GetTestDataPath

from flowgraph.adapters import ADAPTERS
from flowgraph.adapters.data_types import DIRECTORY, LIST_STR, TABLE_DOCUMENT
from flowgraph.adapters.files import READ_DIRECTORY_FILES, DirectoryReadError
from flowgraph.adapters.readers import (
    LOAD_MESHIO,
    LOAD_MESHLANE,
    LOAD_MUSCAT,
    READ_TABLE,
    MeshLoadError,
    TableReadError,
)
from flowgraph.adapters.simple_sources import SET_STRING
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import WorkflowEdge, WorkflowExecutor, WorkflowGraph
from flowgraph.application.workflow_io import workflow_from_json, workflow_to_dict
from flowgraph.domain.mesh_document import MeshDocument


@pytest.fixture
def temporal_xdmf(tmp_path: Path) -> Path:
    source = tmp_path / "series.xdmf"
    mesh = CreateMeshOfTriangles([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 1.0]], [[0, 1, 2]])
    writer = XdmfWriter(str(source))
    writer.SetBinary(False)
    writer.SetTemporal()
    writer.Open()
    try:
        for time in (2.5, 8.0, 13.0):
            writer.Write(
                mesh, Time=time, PointFieldsNames=["value"], PointFields=[np.full(3, time)]
            )
    finally:
        writer.Close()
    return source


@pytest.mark.parametrize(
    ("selection", "expected"), [(None, 13.0), ("first", 2.5), ("last", 13.0), ("all", 13.0)]
)
def test_load_muscat_selects_xdmf_snapshots(
    temporal_xdmf: Path, selection: str | None, expected: float
) -> None:
    parameters = {"path": str(temporal_xdmf)}
    if selection is not None:
        parameters["timestep_to_read"] = selection
    registry = create_node_registry()
    graph = WorkflowGraph([LOAD_MUSCAT.create_instance("reader", parameters=parameters)])
    restored = workflow_from_json(json.dumps(workflow_to_dict(graph)), registry)

    output = WorkflowExecutor(registry).run(restored).node_outputs["reader"]

    assert isinstance(output["mesh"], MeshDocument)
    np.testing.assert_array_equal(output["mesh"].mesh.nodeFields["value"], [expected] * 3)
    series = output["mesh_series"]
    if selection == "all":
        assert tuple(time for time, _ in series) == (2.5, 8.0, 13.0)
        assert output["mesh"] is series[-1][1]
        for time, snapshot in series:
            np.testing.assert_array_equal(snapshot.mesh.nodeFields["value"], [time] * 3)
            assert not snapshot.mesh.nodeFields["value"].flags.writeable
    else:
        assert series == ()


def test_connected_muscat_timestep_overrides_saved_setting(temporal_xdmf: Path) -> None:
    registry = create_node_registry()
    reader = LOAD_MUSCAT.create_instance("reader", parameters={"path": temporal_xdmf})
    graph = WorkflowGraph(
        [SET_STRING.create_instance("mode", parameters={"value": "first"}), reader]
    )
    graph.add_edge(WorkflowEdge("mode", "value", "reader", "timestep_to_read"), registry)

    output = WorkflowExecutor(registry).run(graph).node_outputs["reader"]

    np.testing.assert_array_equal(output["mesh"].mesh.nodeFields["value"], [2.5] * 3)
    assert reader.parameters["timestep_to_read"] == "last"


@pytest.mark.parametrize("selection", ["first", "last", "all"])
def test_load_muscat_static_xdmf_has_no_time(tmp_path: Path, selection: str) -> None:
    source = tmp_path / "static.xdmf"
    meshio.write(
        source,
        meshio.Mesh(
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 1.0]], [("triangle", [[0, 1, 2]])]
        ),
        data_format="XML",
    )

    result = LOAD_MUSCAT.executor({"path": source}, {"timestep_to_read": selection})

    assert result["mesh"].mesh.GetNumberOfNodes() == 3
    assert result["mesh_series"] == (((None, result["mesh"]),) if selection == "all" else ())


def test_load_muscat_reads_ut_results_at_each_available_time() -> None:
    source = Path(GetTestDataPath()) / "UtExample" / "cube.ut"

    output = LOAD_MUSCAT.executor({"path": source}, {"timestep_to_read": "all"})

    series = output["mesh_series"]
    assert len(series) > 1
    assert output["mesh"] is series[-1][1]
    assert not np.array_equal(
        series[0][1].mesh.nodeFields["U1"], series[-1][1].mesh.nodeFields["U1"]
    )


def test_load_muscat_rejects_unknown_timestep(temporal_xdmf: Path) -> None:
    with pytest.raises(MeshLoadError, match="expected first, last, or all"):
        LOAD_MUSCAT.executor({"path": temporal_xdmf}, {"timestep_to_read": "unknown"})


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


def test_read_table_reads_an_excel_workbook(tmp_path: Path) -> None:
    import pandas as pd

    source = tmp_path / "input.xlsx"
    pd.DataFrame({"name": ["Ada", "Grace"], "age": [36, 28]}).to_excel(
        source, index=False, sheet_name="Employees"
    )

    outputs = READ_TABLE.executor({}, {"path": source, "sheet_name": "Employees"})

    assert outputs == {"data": {"name": ["Ada", "Grace"], "age": [36, 28]}}


def test_read_table_uses_default_sheet_name(tmp_path: Path) -> None:
    import pandas as pd

    source = tmp_path / "input.xlsx"
    pd.DataFrame({"name": ["Ada"], "age": [36]}).to_excel(source, index=False)

    outputs = READ_TABLE.executor({}, {"path": source})

    assert outputs == {"data": {"name": ["Ada"], "age": [36]}}


def test_read_table_rejects_missing_source(tmp_path: Path) -> None:
    with pytest.raises(TableReadError, match="does not exist or is not a file"):
        READ_TABLE.executor({}, {"path": tmp_path / "missing.xlsx"})


def test_read_table_exposes_symmetric_table_configuration() -> None:
    assert ADAPTERS.require("read-table") is READ_TABLE
    assert READ_TABLE.output("data").data_type is TABLE_DOCUMENT
    assert [
        (parameter.name, parameter.default, parameter.port) for parameter in READ_TABLE.parameters
    ] == [
        ("path", "input_pandas.xlsx", True),
        ("sheet_name", "Sheet1", True),
    ]


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

    assert result == {
        "files": ["alpha.csv", "zeta.txt"],
        "files_full_paths": [
            str(tmp_path / "alpha.csv"),
            str(tmp_path / "zeta.txt"),
        ],
    }


def test_read_directory_files_filters_with_inclusive_and_exclusive_regexes(tmp_path: Path) -> None:
    for filename in ("data.csv", "report.txt", "report.generated.csv", "image.png"):
        (tmp_path / filename).touch()

    result = READ_DIRECTORY_FILES.executor(
        {"path": tmp_path},
        {"include_pattern": r"\.(csv|txt)$", "exclude_pattern": "generated"},
    )

    assert result == {
        "files": ["data.csv", "report.txt"],
        "files_full_paths": [
            str(tmp_path / "data.csv"),
            str(tmp_path / "report.txt"),
        ],
    }


def test_read_directory_files_rejects_invalid_pattern_rules(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Invalid filename regular expression"):
        READ_DIRECTORY_FILES.executor({"path": tmp_path}, {"include_pattern": "["})


def test_read_directory_files_rejects_a_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(DirectoryReadError, match="does not exist or is not a directory"):
        READ_DIRECTORY_FILES.executor({"path": tmp_path / "missing"}, {})


def test_read_directory_files_is_registered_with_path_and_list_text_output() -> None:
    assert ADAPTERS.require("read-directory-files") is READ_DIRECTORY_FILES
    assert [(port.name, port.data_type) for port in READ_DIRECTORY_FILES.inputs] == [
        ("path", DIRECTORY)
    ]
    assert READ_DIRECTORY_FILES.parameters[0].kind is DIRECTORY
    assert [(port.name, port.data_type) for port in READ_DIRECTORY_FILES.outputs] == [
        ("files", LIST_STR),
        ("files_full_paths", LIST_STR),
    ]
    assert [parameter.name for parameter in READ_DIRECTORY_FILES.parameters] == [
        "path",
        "include_pattern",
        "exclude_pattern",
    ]
    assert READ_DIRECTORY_FILES.parameters[0].port is True
    assert READ_DIRECTORY_FILES.parameters[1].port is False
    assert READ_DIRECTORY_FILES.parameters[2].port is False


def test_read_directory_path_parameter_round_trips(tmp_path: Path) -> None:
    from flowgraph.application.node_registry import create_node_registry

    registry = create_node_registry()
    node = READ_DIRECTORY_FILES.create_instance("listing", parameters={"path": str(tmp_path)})
    assert isinstance(node.parameters["path"], Path)
    serialized = json.dumps(workflow_to_dict(WorkflowGraph([node])))
    restored = workflow_from_json(serialized, registry)
    assert restored.require_node("listing").parameters["path"] == str(tmp_path)
    from flowgraph.application.workflow_core import WorkflowExecutor

    result = WorkflowExecutor(registry).run(restored)
    assert result.node_outputs["listing"] == {"files": [], "files_full_paths": []}
