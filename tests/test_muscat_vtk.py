from pathlib import Path

from flowgraph.adapters.readers import LOAD_MUSCAT


def test_muscat_document_projects_to_vtk() -> None:
    from Muscat.TestData import GetTestDataPath

    outputs = LOAD_MUSCAT.executor({"path": Path(GetTestDataPath()) / "square2D.mesh"}, {})
    assert outputs is not None
    document = outputs["mesh"]
    grid = document.to_vtk_unstructured_grid()

    assert grid.GetNumberOfPoints() == document.mesh.GetNumberOfNodes()
    assert grid.GetNumberOfCells() == document.mesh.GetNumberOfElements()
    assert grid.GetPointData().GetArray("flowgraph_node_id") is not None
    assert grid.GetCellData().GetArray("flowgraph_element_id") is not None
