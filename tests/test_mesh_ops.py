import numpy as np
import pytest
from Muscat.LinAlg.Transform import Transform
from Muscat.MeshContainers import ElementsDescription as ED
from Muscat.MeshContainers.ElementsContainers import ElementsContainer
from Muscat.MeshContainers.Mesh import Mesh

from flowgraph.adapters import ADAPTERS
from flowgraph.adapters.data_types import MESH_DOCUMENT, TRANSFORM_T, VEC3D
from flowgraph.adapters.filters import CREATE_MUSCAT_ELEMENT_FILTER
from flowgraph.adapters.mesh_ops import (
    APPLY_TRANSFORM_NODE,
    CREATE_TAG_NODE,
    DELAUNAY_3D_NODE,
    MERGE_TAGS_NODE,
    QUAD_TO_LIN_NODE,
    REMOVE_TAG_NODE,
    RENAME_TAG_NODE,
    TRANSFORM_NODE,
)
from flowgraph.domain.mesh_document import MeshDocument


def test_mesh_transform_exposes_transform_and_direction_parameters() -> None:
    assert ADAPTERS.require("transform") is TRANSFORM_NODE
    assert TRANSFORM_NODE.output("Transform").data_type is TRANSFORM_T
    assert [parameter.name for parameter in TRANSFORM_NODE.parameters] == [
        "translation",
        "first",
        "second",
        "keepNormalized",
        "keepOrthogonal",
    ]
    assert all(parameter.kind is VEC3D for parameter in TRANSFORM_NODE.parameters[:3])
    assert [parameter.default for parameter in TRANSFORM_NODE.parameters[3:]] == [True, True]
    assert all(parameter.port is False for parameter in TRANSFORM_NODE.parameters[3:])
    assert TRANSFORM_NODE.input("keepNormalized") is None
    assert TRANSFORM_NODE.input("keepOrthogonal") is None


@pytest.mark.parametrize("node", [RENAME_TAG_NODE, MERGE_TAGS_NODE, REMOVE_TAG_NODE])
def test_tag_nodes_expose_entity_dropdown(node) -> None:
    entity = next(parameter for parameter in node.parameters if parameter.name == "entity")

    assert entity.kind.id == "str"
    assert [(option.value, option.label) for option in entity.options] == [
        ("element", "Element"),
        ("node", "Node"),
    ]


def test_create_tag_node_exposes_mesh_filter_and_exported_tag_name() -> None:
    assert ADAPTERS.require("create-tag") is CREATE_TAG_NODE
    assert [port.name for port in CREATE_TAG_NODE.inputs] == ["mesh", "filter", "tagName"]
    assert CREATE_TAG_NODE.input("mesh").data_type is MESH_DOCUMENT
    assert (
        CREATE_TAG_NODE.input("filter").data_type
        is CREATE_MUSCAT_ELEMENT_FILTER.output("filter").data_type
    )
    assert CREATE_TAG_NODE.output("mesh").data_type is MESH_DOCUMENT
    assert [(parameter.name, parameter.port) for parameter in CREATE_TAG_NODE.parameters] == [
        ("tagName", True),
        ("nodeTag", False),
        ("overwrite", False),
    ]
    assert CREATE_TAG_NODE.parameters[1].label == "Node tag (Element tag if False)"


def test_quad_to_lin_node_exposes_mesh_ports_and_parameters() -> None:
    assert ADAPTERS.require("quad-to-lin") is QUAD_TO_LIN_NODE
    assert [port.name for port in QUAD_TO_LIN_NODE.inputs] == ["inputMesh"]
    assert [port.name for port in QUAD_TO_LIN_NODE.outputs] == ["outputMesh"]
    assert QUAD_TO_LIN_NODE.input("inputMesh").data_type is MESH_DOCUMENT
    assert QUAD_TO_LIN_NODE.output("outputMesh").data_type is MESH_DOCUMENT
    assert [
        (parameter.name, parameter.default, parameter.port)
        for parameter in QUAD_TO_LIN_NODE.parameters
    ] == [
        ("divideQuadElements", True, False),
        ("linearizedMiddlePoints", False, False),
    ]


def test_quad_to_lin_node_converts_quadratic_elements_without_mutating_input() -> None:
    source_mesh = Mesh()
    source_mesh.SetNodes(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0.5, 0, 0], [0.5, 0.5, 0], [0, 0.5, 0]],
        generateOriginalIDs=True,
    )
    elements = ElementsContainer(ED.ElementType.Triangle_6)
    elements.AddNewElements([[0, 1, 2, 3, 4, 5]])
    source_mesh.elements.AddContainer(elements)
    source = MeshDocument(source_mesh)

    result = QUAD_TO_LIN_NODE.executor(
        {"inputMesh": source}, {"divideQuadElements": True, "linearizedMiddlePoints": True}
    )["outputMesh"]

    assert isinstance(result, MeshDocument)
    assert result is not source
    assert result.mesh.GetNumberOfElements() == 4
    assert result.mesh.elements[ED.ElementType.Triangle_3].GetNumberOfElements() == 4
    np.testing.assert_array_equal(
        source.mesh.elements[ED.ElementType.Triangle_6].connectivity, [[0, 1, 2, 3, 4, 5]]
    )
    np.testing.assert_array_equal(result.mesh.nodes[3:6], [[0.5, 0, 0], [0.5, 0.5, 0], [0, 0.5, 0]])


def test_mesh_transform_sets_offset_and_all_directions() -> None:
    outputs = TRANSFORM_NODE.executor(
        {},
        {
            "translation": [1, 2, 3],
            "first": [0, 1, 0],
            "second": [0, 0, 1],
            "third": [1, 0, 0],
            "keepNormalized": False,
            "keepOrthogonal": False,
        },
    )

    transform = outputs["Transform"]
    assert isinstance(transform, Transform)
    np.testing.assert_array_equal(transform.offset, [1, 2, 3])
    np.testing.assert_array_equal(
        transform.RMatrix,
        [[0, 1, 0], [0, 0, 1], [1, 0, 0]],
    )
    assert transform.keepNormalized is False
    assert transform.keepOrthogonal is False


def test_apply_transform_node_transforms_mesh_without_mutating_input() -> None:
    source_mesh = Mesh()
    source_mesh.SetNodes([[1, 2, 3], [4, 5, 6]], generateOriginalIDs=True)
    source = MeshDocument(source_mesh)
    transform = Transform(offset=[1, 1, 1])

    outputs = APPLY_TRANSFORM_NODE.executor({"mesh": source, "Transform": transform}, {})

    assert APPLY_TRANSFORM_NODE.input("mesh").data_type is MESH_DOCUMENT
    result = outputs["mesh"]
    assert isinstance(result, MeshDocument)
    assert result is not source
    np.testing.assert_array_equal(result.mesh.nodes, [[0, 1, 2], [3, 4, 5]])
    np.testing.assert_array_equal(source.mesh.nodes, [[1, 2, 3], [4, 5, 6]])


def test_apply_transform_node_exposes_inverse_transform_checkbox() -> None:
    inverse = next(
        parameter for parameter in APPLY_TRANSFORM_NODE.parameters if parameter.name == "inverse"
    )

    assert inverse.kind.id == "boolean"
    assert inverse.label == "Apply inverse transform"
    assert inverse.default is False
    assert inverse.port is False


def test_apply_transform_node_can_apply_inverse_transform() -> None:
    source_mesh = Mesh()
    source_mesh.SetNodes([[1, 2, 3], [4, 5, 6]], generateOriginalIDs=True)
    source_mesh.nodeFields["vectors"] = np.array([[1, 0, 0], [0, 1, 0]])
    source = MeshDocument(source_mesh)
    transform = Transform(offset=[1, 1, 1], first=[0, 1, 0], second=[-1, 0, 0])

    result = APPLY_TRANSFORM_NODE.executor(
        {"mesh": source, "Transform": transform}, {"inverse": True}
    )["mesh"]

    np.testing.assert_array_equal(result.mesh.nodes, [[-1, 2, 4], [-4, 5, 7]])
    np.testing.assert_array_equal(result.mesh.nodeFields["vectors"], [[0, 1, 0], [-1, 0, 0]])
    np.testing.assert_array_equal(source.mesh.nodes, [[1, 2, 3], [4, 5, 6]])


def test_delaunay_3d_preserves_points_node_fields_and_node_tags() -> None:
    source_mesh = Mesh()
    points = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]
    source_mesh.SetNodes(points, generateOriginalIDs=True)
    source_mesh.nodeFields["temperature"] = np.array([10, 20, 30, 40])
    source_mesh.nodesTags.CreateTag("boundary").SetIds([0, 1, 2])
    source = MeshDocument(source_mesh)

    result = DELAUNAY_3D_NODE.executor({"meshDocument": source}, {})["meshDocument"]

    assert DELAUNAY_3D_NODE.input("meshDocument").data_type is MESH_DOCUMENT
    assert isinstance(result, MeshDocument)
    assert result is not source
    np.testing.assert_array_equal(result.mesh.nodes, points)
    np.testing.assert_array_equal(result.mesh.nodeFields["temperature"], [10, 20, 30, 40])
    np.testing.assert_array_equal(result.mesh.nodesTags["boundary"].GetIds(), [0, 1, 2])
    assert result.mesh.GetNumberOfElements() == 1
    assert sorted(result.mesh.elements[ED.ElementType.Tetrahedron_4].connectivity[0]) == [
        0,
        1,
        2,
        3,
    ]
    assert source.mesh.GetNumberOfElements() == 0


def test_apply_transform_node_transforms_three_component_node_and_element_fields() -> None:
    source_mesh = Mesh()
    source_mesh.SetNodes([[1, 2, 3], [4, 5, 6]], generateOriginalIDs=True)
    source_mesh.nodeFields["vectors"] = np.array([[1, 0, 0], [0, 1, 0]])
    source_mesh.nodeFields["scalars"] = np.array([[1], [2]])
    source_mesh.elemFields["vectors"] = np.array([[0, 0, 1]])
    source_mesh.elemFields["tensor"] = np.ones((1, 2, 2))
    source = MeshDocument(source_mesh)
    transform = Transform(offset=[10, 20, 30], first=[0, 1, 0], second=[-1, 0, 0])

    result = APPLY_TRANSFORM_NODE.executor({"mesh": source, "Transform": transform}, {})["mesh"]

    np.testing.assert_array_equal(result.mesh.nodeFields["vectors"], [[0, -1, 0], [1, 0, 0]])
    np.testing.assert_array_equal(result.mesh.elemFields["vectors"], [[0, 0, 1]])
    np.testing.assert_array_equal(result.mesh.nodeFields["scalars"], [[1], [2]])
    np.testing.assert_array_equal(result.mesh.elemFields["tensor"], np.ones((1, 2, 2)))
    np.testing.assert_array_equal(source.mesh.nodeFields["vectors"], [[1, 0, 0], [0, 1, 0]])


def test_apply_transform_node_can_skip_vector_fields() -> None:
    source_mesh = Mesh()
    source_mesh.SetNodes([[1, 2, 3]], generateOriginalIDs=True)
    source_mesh.nodeFields["vectors"] = np.array([[1, 0, 0]])
    source = MeshDocument(source_mesh)
    transform = Transform(first=[0, 1, 0], second=[-1, 0, 0])

    result = APPLY_TRANSFORM_NODE.executor(
        {"mesh": source, "Transform": transform}, {"onVectorFields": False}
    )["mesh"]

    np.testing.assert_array_equal(result.mesh.nodeFields["vectors"], [[1, 0, 0]])


def _tagged_mesh() -> MeshDocument:
    mesh = Mesh()
    mesh.SetNodes([[0, 0, 0], [1, 0, 0], [0, 1, 0]], generateOriginalIDs=True)
    mesh.nodesTags.CreateTag("left").SetIds([0, 1])
    mesh.nodesTags.CreateTag("right").SetIds([1, 2])

    elements = ElementsContainer(ED.ElementType.Triangle_3)
    elements.AddNewElements([[0, 1, 2]])
    elements.tags.CreateTag("surface").SetIds([0])
    mesh.elements.AddContainer(elements)
    return MeshDocument(mesh)


@pytest.mark.parametrize(
    ("node", "entity", "tag_names"),
    [
        (RENAME_TAG_NODE, "node", {"renamed"}),
        (RENAME_TAG_NODE, "element", {"renamed"}),
    ],
)
def test_rename_tag_node_supports_node_and_element_tags(node, entity, tag_names) -> None:
    source = _tagged_mesh()
    parameters = {
        "entity": entity,
        "tag": "left" if entity == "node" else "surface",
        "newTag": "renamed",
    }

    result = node.executor({"mesh": source}, parameters)["mesh"]

    collection = (
        result.mesh.nodesTags
        if entity == "node"
        else result.mesh.elements[ED.ElementType.Triangle_3].tags
    )
    assert "renamed" in {tag.name for tag in collection}
    assert (
        "right" in {tag.name for tag in collection}
        if entity == "node"
        else "surface" not in {tag.name for tag in collection}
    )
    source_collection = (
        source.mesh.nodesTags
        if entity == "node"
        else source.mesh.elements[ED.ElementType.Triangle_3].tags
    )
    assert parameters["tag"] in {tag.name for tag in source_collection}


@pytest.mark.parametrize("entity", ["node", "element"])
def test_merge_tag_node_unions_sources_and_removes_sources(entity) -> None:
    source = _tagged_mesh()
    if entity == "element":
        source.mesh.elements[ED.ElementType.Triangle_3].tags.CreateTag("other").SetIds([0])
        source_names = ["surface", "other"]
    else:
        source_names = ["left", "right"]

    result = MERGE_TAGS_NODE.executor(
        {"mesh": source}, {"entity": entity, "sourceTags": source_names, "targetTag": "combined"}
    )["mesh"]

    collection = (
        result.mesh.nodesTags
        if entity == "node"
        else result.mesh.elements[ED.ElementType.Triangle_3].tags
    )
    assert {tag.name for tag in collection} == {"combined"}
    np.testing.assert_array_equal(
        collection["combined"].GetIds(), [0, 1, 2] if entity == "node" else [0]
    )


@pytest.mark.parametrize("entity", ["node", "element"])
def test_remove_tag_node_removes_requested_tag_and_does_not_mutate_input(entity) -> None:
    source = _tagged_mesh()
    tag = "left" if entity == "node" else "surface"

    result = REMOVE_TAG_NODE.executor({"mesh": source}, {"entity": entity, "tag": tag})["mesh"]

    result_collection = (
        result.mesh.nodesTags
        if entity == "node"
        else result.mesh.elements[ED.ElementType.Triangle_3].tags
    )
    source_collection = (
        source.mesh.nodesTags
        if entity == "node"
        else source.mesh.elements[ED.ElementType.Triangle_3].tags
    )
    assert tag not in result_collection
    assert tag in source_collection


@pytest.mark.parametrize("node_tag", [False, True])
def test_create_tag_node_tags_filter_selection_without_mutating_input(node_tag) -> None:
    source = _tagged_mesh()
    element_filter = CREATE_MUSCAT_ELEMENT_FILTER.executor(
        {}, {"dimensionality": [2], "element_types": ["Triangle_3"], "ntag": [], "etag": []}
    )["filter"]

    result = CREATE_TAG_NODE.executor(
        {"mesh": source, "filter": element_filter}, {"tagName": "selected", "nodeTag": node_tag}
    )["mesh"]

    assert result is not source
    if node_tag:
        assert result.mesh.nodesTags["selected"].GetIds().tolist() == [0, 1, 2]
        assert "selected" not in source.mesh.nodesTags
    else:
        tags = result.mesh.elements[ED.ElementType.Triangle_3].tags
        assert tags["selected"].GetIds().tolist() == [0]
        assert "selected" not in source.mesh.elements[ED.ElementType.Triangle_3].tags


@pytest.mark.parametrize("node_tag", [False, True])
def test_create_tag_node_rejects_existing_tags_without_overwrite(node_tag) -> None:
    source = _tagged_mesh()
    element_filter = CREATE_MUSCAT_ELEMENT_FILTER.executor(
        {}, {"dimensionality": [2], "element_types": ["Triangle_3"], "ntag": [], "etag": []}
    )["filter"]
    existing_name = "left" if node_tag else "surface"

    with pytest.raises(ValueError, match="already exists"):
        CREATE_TAG_NODE.executor(
            {"mesh": source, "filter": element_filter},
            {"tagName": existing_name, "nodeTag": node_tag},
        )


@pytest.mark.parametrize(
    ("node", "parameters"),
    [
        (RENAME_TAG_NODE, {"entity": "node", "tag": "missing", "newTag": "new"}),
        (REMOVE_TAG_NODE, {"entity": "element", "tag": "missing"}),
        (MERGE_TAGS_NODE, {"entity": "node", "sourceTags": ["left"], "targetTag": "left"}),
        (MERGE_TAGS_NODE, {"entity": "node", "sourceTags": [], "targetTag": "new"}),
    ],
)
def test_tag_nodes_reject_invalid_operations_without_mutating_input(node, parameters) -> None:
    source = _tagged_mesh()
    before = [tag.name for tag in source.mesh.nodesTags]

    with pytest.raises(ValueError):
        node.executor({"mesh": source}, parameters)

    assert [tag.name for tag in source.mesh.nodesTags] == before
