"""Unused mesh point removal preserves metadata and source documents."""

import numpy as np
import pytest
from Muscat.MeshContainers import ElementsDescription as ED
from Muscat.MeshContainers.Mesh import Mesh

from flowgraph.adapters import ADAPTERS
from flowgraph.adapters.data_types import MESH_DOCUMENT
from flowgraph.adapters.mesh_ops import REMOVE_LONELY_NODES_NODE
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import WorkflowExecutor, WorkflowGraph
from flowgraph.application.workflow_io import load_workflow, save_workflow
from flowgraph.domain.mesh_document import MeshDocument


def test_remove_lonely_nodes_is_registered_under_mesh_ops() -> None:
    mesh_tools = next(group for group in ADAPTERS.groups if group.label == "Mesh Tools")
    mesh_ops = next(group for group in mesh_tools.subgroups if group.label == "Mesh Ops")
    assert REMOVE_LONELY_NODES_NODE in mesh_ops.node_definitions
    assert ADAPTERS.require("remove-lonely-nodes") is REMOVE_LONELY_NODES_NODE
    assert REMOVE_LONELY_NODES_NODE.input("mesh").data_type is MESH_DOCUMENT
    assert REMOVE_LONELY_NODES_NODE.output("mesh").data_type is MESH_DOCUMENT
    assert REMOVE_LONELY_NODES_NODE.parameters == ()


def test_cleanup_remaps_connectivity_fields_tags_and_ids_without_mutation() -> None:
    mesh = Mesh()
    mesh.SetNodes([[9, 9, 9], [0, 0, 0], [8, 8, 8], [1, 0, 0], [0, 1, 0]], generateOriginalIDs=True)
    mesh.originalIDNodes = np.array([10, 20, 30, 40, 50])
    elements = mesh.GetElementsOfType(ED.ElementType.Triangle_3)
    elements.AddNewElements(np.array([[1, 3, 4]]), np.array([77]))
    elements.tags.CreateTag("surface").SetIds([0])
    mesh.nodesTags.CreateTag("mixed").SetIds([0, 3, 4])
    mesh.nodesTags.CreateTag("unused").SetIds([2])
    mesh.nodeFields["temperature"] = np.arange(5.0)
    mesh.nodeFields["vector"] = np.arange(15.0).reshape(5, 3)
    mesh.elemFields["material"] = np.array([42])
    source = MeshDocument(mesh)

    result = REMOVE_LONELY_NODES_NODE.executor({"mesh": source}, {})["mesh"]

    assert result is not source and result.mesh is not mesh
    np.testing.assert_array_equal(result.mesh.nodes, mesh.nodes[[1, 3, 4]])
    np.testing.assert_array_equal(result.mesh.originalIDNodes, [20, 40, 50])
    np.testing.assert_array_equal(
        result.mesh.elements[ED.ElementType.Triangle_3].connectivity, [[0, 1, 2]]
    )
    np.testing.assert_array_equal(result.mesh.nodesTags["mixed"].GetIds(), [1, 2])
    assert len(result.mesh.nodesTags["unused"]) == 0
    for name, field in mesh.nodeFields.items():
        np.testing.assert_array_equal(result.mesh.nodeFields[name], field[[1, 3, 4]])
        assert len(field) == 5
    for name, field in mesh.elemFields.items():
        np.testing.assert_array_equal(result.mesh.elemFields[name], field)
    result_elements = result.mesh.elements[ED.ElementType.Triangle_3]
    np.testing.assert_array_equal(result_elements.originalIds, [77])
    np.testing.assert_array_equal(result_elements.tags["surface"].GetIds(), [0])
    assert mesh.GetNumberOfNodes() == 5
    np.testing.assert_array_equal(elements.connectivity, [[1, 3, 4]])
    np.testing.assert_array_equal(mesh.originalIDNodes, [10, 20, 30, 40, 50])
    np.testing.assert_array_equal(mesh.nodesTags["mixed"].GetIds(), [0, 3, 4])


@pytest.mark.parametrize("count", [0, 3])
def test_cleanup_mesh_without_elements_removes_all_points(count) -> None:
    mesh = Mesh()
    mesh.SetNodes(np.zeros((count, 3)), generateOriginalIDs=True)
    source = MeshDocument(mesh)
    result = REMOVE_LONELY_NODES_NODE.executor({"mesh": source}, {})["mesh"]
    assert result.mesh.nodes.shape == (0, 3)
    assert result.mesh.GetNumberOfElements() == 0
    assert result.get_muscat_node_ids().shape == (0,)
    assert source.mesh.GetNumberOfNodes() == count


def test_cleanup_node_round_trips_and_executes_in_workflow(tmp_path) -> None:
    from flowgraph.adapters.mesh_creation_tools import CREATE_CUBE_NODE
    from flowgraph.application.workflow_core import WorkflowEdge

    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            CREATE_CUBE_NODE.create_instance("source"),
            REMOVE_LONELY_NODES_NODE.create_instance("clean"),
        ]
    )
    graph.add_edge(WorkflowEdge("source", "mesh", "clean", "mesh"), registry)
    path = tmp_path / "cleanup.json"
    save_workflow(graph, path)
    result = WorkflowExecutor(registry).run(load_workflow(path, registry))
    source = result.node_outputs["source"]["mesh"].mesh
    clean = result.node_outputs["clean"]["mesh"].mesh
    np.testing.assert_array_equal(clean.nodes, source.nodes)
    assert clean.GetNumberOfElements() == source.GetNumberOfElements()
    np.testing.assert_array_equal(
        clean.nodeFields["flowgraph_node_id"], source.nodeFields["flowgraph_node_id"]
    )


def test_structured_mesh_cleanup_preserves_element_tags_and_connectivity() -> None:
    from Muscat.MeshTools.MeshCreationTools import CreateCube

    mesh = CreateCube(dimensions=[3, 3, 3])
    bulk = mesh.elements[ED.ElementType.Hexahedron_8]
    bulk.tags.CreateTag("bulk-selection").SetIds([0, 2])
    source = MeshDocument(mesh)
    result = REMOVE_LONELY_NODES_NODE.executor({"mesh": source}, {})["mesh"]
    cleaned = result.mesh.elements[ED.ElementType.Hexahedron_8]
    np.testing.assert_array_equal(cleaned.connectivity, bulk.connectivity)
    np.testing.assert_array_equal(cleaned.tags["bulk-selection"].GetIds(), [0, 2])
    np.testing.assert_array_equal(cleaned.originalIds, bulk.originalIds)
