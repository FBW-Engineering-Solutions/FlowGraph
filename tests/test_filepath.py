import json
from pathlib import Path

import pytest

from flowgraph.domain.filepath import FilePath


def test_file_path_accepts_one_or_many_paths_and_delegates_to_primary() -> None:
    file_path = FilePath("mesh.mesh")
    assert file_path.files == [Path("mesh.mesh")]
    assert file_path.primary == Path("mesh.mesh")
    assert file_path.name == "mesh.mesh"
    assert file_path.suffix == ".mesh"
    assert str(file_path) == "mesh.mesh"

    multiple = FilePath(["mesh.mesh", "mesh.xdmf"])
    assert multiple.files == [Path("mesh.mesh"), Path("mesh.xdmf")]


def test_file_path_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="at least one file"):
        FilePath([])


def test_file_path_adds_and_compacts_dependent_files_in_order() -> None:
    file_path = FilePath("mesh.mesh")
    file_path.AddDependentFiles(["mesh.xdmf", "mesh.h5"])
    file_path.AddDependentFiles("mesh.xdmf")

    file_path.Compact()

    assert file_path.files == [Path("mesh.mesh"), Path("mesh.xdmf"), Path("mesh.h5")]


def test_file_path_json_round_trip_preserves_all_paths() -> None:
    file_path = FilePath(["mesh.mesh", "mesh.xdmf"])

    encoded = file_path.to_json(sort_keys=True)
    assert json.loads(encoded) == {"files": ["mesh.mesh", "mesh.xdmf"]}
    assert FilePath.from_json(encoded).files == file_path.files


@pytest.mark.parametrize("payload", ["{}", '{"files": []}', '{"files": [1]}', "[]"])
def test_file_path_rejects_malformed_json(payload: str) -> None:
    with pytest.raises(ValueError, match="files"):
        FilePath.from_json(payload)
