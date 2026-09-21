import numpy as np
from Muscat.MeshContainers import ElementsDescription as ED
from Muscat.MeshContainers.Mesh import Mesh

from flowgraph.adapters import ADAPTERS
from flowgraph.adapters.data_types import VEC2DI, VEC3DI
from flowgraph.adapters.mesh_creation_tools import (
    CREATE_0D_ELEMENTS_NODE,
    CREATE_CUBE_NODE,
    CREATE_MESH_FROM_CELLS_DICT_NODE,
    CREATE_MESH_OF_NODE,
    CREATE_SQUARE_NODE,
    MIRROR_MESH_NODE,
    SUBDIVIDE_MESH_NODE,
)
from flowgraph.domain.mesh_document import MeshDocument


def test_mesh_creation_nodes_are_registered() -> None:
    node_ids = [node.id for node in ADAPTERS.node_definitions]

    assert CREATE_SQUARE_NODE.id in node_ids
    assert CREATE_CUBE_NODE.id in node_ids
    assert CREATE_MESH_OF_NODE.id in node_ids
    assert CREATE_0D_ELEMENTS_NODE.id in node_ids


def test_mesh_creation_boolean_checks_are_not_ports() -> None:
    assert CREATE_SQUARE_NODE.input("ofTriangles") is None
    assert MIRROR_MESH_NODE.input("propagateToNodeFields") is None
    assert SUBDIVIDE_MESH_NODE.input("level") is not None


def test_create_mesh_from_cells_dict_metadata_are_input_ports() -> None:
    parameter_names = ("pointFields", "cellFields", "originalIds", "cellsOriginalIds")

    assert [port.name for port in CREATE_MESH_FROM_CELLS_DICT_NODE.inputs] == [
        "points",
        "cellsDict",
        *parameter_names,
    ]
    assert [parameter.name for parameter in CREATE_MESH_FROM_CELLS_DICT_NODE.parameters] == [
        "cellFieldInDictOrder"
    ]


def test_create_mesh_from_cells_dict_forwards_connected_metadata_inputs() -> None:
    result = CREATE_MESH_FROM_CELLS_DICT_NODE.executor(
        {
            "points": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            "cellsDict": {ED.ElementType.Triangle_3: [[0, 1, 2]]},
            "pointFields": {"temperature": np.array([[1.0], [2.0], [3.0]])},
            "cellFields": {"region": np.array([[4]])},
            "originalIds": np.array([7, 8, 9]),
            "cellsOriginalIds": {ED.ElementType.Triangle_3: np.array([10])},
        },
        {},
    )

    mesh = result["mesh"].mesh
    np.testing.assert_array_equal(mesh.originalIDNodes, [7, 8, 9])
    np.testing.assert_array_equal(mesh.nodeFields["temperature"], [[1.0], [2.0], [3.0]])
    np.testing.assert_array_equal(mesh.elements[ED.ElementType.Triangle_3].originalIds, [10])
    np.testing.assert_array_equal(mesh.elemFields["region"], [[4]])


def test_structured_mesh_dimensions_use_integer_vector_types() -> None:
    square_dimensions = next(
        parameter for parameter in CREATE_SQUARE_NODE.parameters if parameter.name == "dimensions"
    )
    cube_dimensions = next(
        parameter for parameter in CREATE_CUBE_NODE.parameters if parameter.name == "dimensions"
    )

    assert square_dimensions.kind is VEC2DI
    assert cube_dimensions.kind is VEC3DI


def test_create_square_returns_a_mesh_document() -> None:
    result = CREATE_SQUARE_NODE.executor({}, {"dimensions": [3, 2], "ofTriangles": True})

    assert isinstance(result["mesh"], MeshDocument)
    assert result["mesh"].mesh.GetNumberOfNodes() == 6
    assert result["mesh"].mesh.GetNumberOfElements() == 10


def test_create_mesh_of_uses_the_selected_element_type() -> None:
    result = CREATE_MESH_OF_NODE.executor(
        {"points": [[0, 0, 0], [1, 0, 0], [0, 1, 0]], "connectivity": [[0, 1, 2]]},
        {"elemName": "Triangle_3"},
    )

    assert isinstance(result["mesh"], MeshDocument)
    assert result["mesh"].mesh.elements[ED.ElementType.Triangle_3].GetNumberOfElements() == 1


def test_create_zero_d_elements_returns_an_elements_container() -> None:
    mesh = Mesh()
    mesh.SetNodes([[0, 0, 0], [1, 0, 0]], generateOriginalIDs=True)

    result = CREATE_0D_ELEMENTS_NODE.executor({"mesh": MeshDocument(mesh)}, {})

    assert result["elements"].GetNumberOfElements() == 2
    assert result["elements"].elementType is ED.ElementType.Point_1


def test_subdivide_mesh_does_not_replace_the_input_document() -> None:
    source = CREATE_SQUARE_NODE.executor({}, {"dimensions": [2, 2]})["mesh"]
    source_nodes = np.array(source.mesh.nodes, copy=True)

    result = SUBDIVIDE_MESH_NODE.executor({"mesh": source}, {"level": 1})["mesh"]

    assert isinstance(result, MeshDocument)
    assert result is not source
    np.testing.assert_array_equal(source.mesh.nodes, source_nodes)
