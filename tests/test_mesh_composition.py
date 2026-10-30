"""Assembly, field averaging/editing, and bidirectional named selections."""

import numpy as np
import pytest
from Muscat.MeshContainers import ElementsDescription as ED
from Muscat.MeshContainers.Filters.FilterObjects import ElementFilter, NodeFilter
from Muscat.MeshContainers.Mesh import Mesh
from Muscat.MeshTools.ConstantRectilinearMeshTools import CreateConstantRectilinearMesh

from flowgraph.adapters import ADAPTERS
from flowgraph.adapters.mesh_composition import FIELD_COMPOSITION_NODES, MESH_COMPOSITION_NODES
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import (
    WorkflowEdge,
    WorkflowExecutor,
    WorkflowGraph,
    WorkflowValidationError,
)
from flowgraph.application.workflow_io import load_workflow, save_workflow
from flowgraph.domain.mesh_document import MeshDocument


def fixture():
    mesh = Mesh()
    mesh.SetNodes(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0], [9.0, 9.0, 9.0]],
        generateOriginalIDs=True,
    )
    elements = mesh.GetElementsOfType(ED.Triangle_3)
    elements.AddNewElements(np.array([[0, 1, 2], [1, 3, 2]]), np.array([20, 30]))
    elements.tags.CreateTag("surface").SetIds([0])
    mesh.nodesTags.CreateTag("boundary").SetIds([0, 1, 2])
    mesh.nodeFields["temperature"] = np.array([0.0, 3.0, 6.0, 9.0, 12.0])
    mesh.elemFields["pressure"] = np.array([2.0, 8.0])
    return MeshDocument(mesh)


def run(node_id, source=None, parameters=None, **inputs):
    if source is not None:
        inputs["mesh"] = source
    return ADAPTERS.require(node_id).executor(inputs, parameters or {})


@pytest.mark.parametrize("definition", (*FIELD_COMPOSITION_NODES, *MESH_COMPOSITION_NODES))
def test_registration_roundtrip_and_catalog(definition, tmp_path):
    assert ADAPTERS.require(definition.id) is definition
    graph = WorkflowGraph([definition.create_instance("node")])
    path = tmp_path / "node.json"
    save_workflow(graph, path)
    assert load_workflow(path, create_node_registry()).nodes[0].definition_id == definition.id


def test_merge_numeric_order_and_field_alignment():
    first, second = fixture(), fixture()
    second.mesh.nodes += 10
    # A lower-dimensional block changes global element ordering after assembly.
    bars = second.mesh.GetElementsOfType(ED.Bar_2)
    bars.AddNewElements(np.array([[0, 1]]), np.array([99]))
    second.mesh.elemFields["pressure"] = np.array([100.0, 20.0, 30.0])
    second.mesh.elemFields["flowgraph_element_id"] = np.arange(3)
    second.mesh.nodeFields["only_second"] = np.ones(5)
    first.mesh.elemFields["only_first"] = np.array([[1.0, 2.0], [3.0, 4.0]])
    result = run("merge-meshes", mesh_10=second, mesh_2=first)["mesh"].mesh
    assert result.GetNumberOfNodes() == 10
    assert result.GetNumberOfElements() == 5
    np.testing.assert_array_equal(result.nodes[:5], first.mesh.nodes)
    np.testing.assert_array_equal(result.elements[ED.Bar_2].connectivity, [[5, 6]])
    np.testing.assert_array_equal(
        result.elements[ED.Triangle_3].connectivity, [[0, 1, 2], [1, 3, 2], [5, 6, 7], [6, 8, 7]]
    )
    np.testing.assert_array_equal(result.elemFields["pressure"], [100, 2, 8, 20, 30])
    np.testing.assert_array_equal(
        result.elemFields["only_first"], [[0, 0], [1, 2], [3, 4], [0, 0], [0, 0]]
    )
    np.testing.assert_array_equal(result.nodeFields["only_second"], [0] * 5 + [1] * 5)
    np.testing.assert_array_equal(result.nodesTags["boundary"].GetIds(), [0, 1, 2, 5, 6, 7])
    np.testing.assert_array_equal(result.elements[ED.Triangle_3].tags["surface"].GetIds(), [0, 2])
    np.testing.assert_array_equal(result.nodeFields["flowgraph_node_id"], np.arange(10))
    np.testing.assert_array_equal(result.elemFields["flowgraph_element_id"], np.arange(5))
    np.testing.assert_array_equal(first.mesh.elemFields["pressure"], [2, 8])
    assert not result.nodes.flags.writeable
    assert not result.elemFields["pressure"].flags.writeable


@pytest.mark.parametrize("fault", ["components", "dimension", "length", "dtype"])
def test_merge_rejects_incompatible_inputs(fault):
    a, b = fixture(), fixture()
    if fault == "components":
        b.mesh.nodeFields["temperature"] = np.ones((5, 2))
    elif fault == "dimension":
        b.mesh.nodes = b.mesh.nodes[:, :2]
    elif fault == "length":
        b.mesh.nodeFields["temperature"] = np.ones(4)
    else:
        b.mesh.nodeFields["temperature"] = np.array(["a"] * 5)
    with pytest.raises(ValueError):
        run("merge-meshes", mesh_1=a, mesh_2=b)
    assert a.mesh.GetNumberOfNodes() == 5


def test_merge_no_input_empty_single_and_structured():
    with pytest.raises(ValueError, match="At least one"):
        run("merge-meshes")
    empty = MeshDocument(Mesh())
    assert run("merge-meshes", mesh_1=empty)["mesh"].mesh.GetNumberOfNodes() == 0
    source = MeshDocument(
        CreateConstantRectilinearMesh([2, 2, 2], [0.0, 0.0, 0.0], [1.0, 1.0, 1.0])
    )
    result = run("merge-meshes", mesh_1=source, mesh_2=source)["mesh"].mesh
    assert result.GetNumberOfElements() == 2
    assert result.GetNumberOfNodes() == 16
    assert source.mesh.GetNumberOfNodes() == 8


@pytest.mark.parametrize("components", [1, 3])
@pytest.mark.parametrize("dtype", [np.int32, np.float32, np.complex128])
def test_field_average_both_directions(components, dtype):
    source = fixture()
    node = np.array([0, 3, 6, 9, 12], dtype=dtype)
    elem = np.array([2, 8], dtype=dtype)
    if components == 3:
        node = np.repeat(node[:, None], 3, axis=1)
        elem = np.repeat(elem[:, None], 3, axis=1)
    source.mesh.nodeFields["temperature"] = node
    source.mesh.elemFields["pressure"] = elem
    a = run("nodal-to-element-field", source, {"fieldName": "temperature"})
    b = run("element-to-nodal-field", source, {"fieldName": "pressure"})
    expected_a, expected_b = np.array([3.0, 6.0]), np.array([2.0, 5.0, 5.0, 8.0, 0.0])
    if components == 3:
        expected_a, expected_b = (
            np.repeat(expected_a[:, None], 3, axis=1),
            np.repeat(expected_b[:, None], 3, axis=1),
        )
    np.testing.assert_allclose(a["field"], expected_a)
    np.testing.assert_allclose(b["field"], expected_b)
    assert not a["field"].flags.writeable
    assert not b["field"].flags.writeable
    assert "temperature" not in source.mesh.elemFields
    assert "pressure" not in source.mesh.nodeFields
    assert np.shares_memory(a["mesh"].mesh.nodes, source.mesh.nodes)


def test_field_conversion_target_removal_dimension_and_conflicts():
    source = fixture()
    a = run(
        "nodal-to-element-field",
        source,
        {"fieldName": "temperature", "targetName": "converted", "removeSource": True},
    )
    assert "temperature" not in a["mesh"].mesh.nodeFields
    assert "temperature" in source.mesh.nodeFields
    assert a["field"] is a["mesh"].mesh.elemFields["converted"]
    with pytest.raises(ValueError, match="already exists"):
        run(
            "nodal-to-element-field", source, {"fieldName": "temperature", "targetName": "pressure"}
        )
    result = run(
        "nodal-to-element-field",
        source,
        {"fieldName": "temperature", "targetName": "pressure", "overwrite": True},
    )
    np.testing.assert_allclose(result["field"], [3, 6])
    np.testing.assert_allclose(
        run("element-to-nodal-field", source, {"fieldName": "pressure", "dimensionality": 1})[
            "field"
        ],
        0,
    )


@pytest.mark.parametrize(
    "node,field",
    [("nodal-to-element-field", "temperature"), ("element-to-nodal-field", "pressure")],
)
@pytest.mark.parametrize("fault", ["missing", "reserved", "shape", "dtype", "dimension", "length"])
def test_conversion_errors(node, field, fault):
    source = fixture()
    params = {"fieldName": field}
    fields = source.mesh.nodeFields if node.startswith("nodal") else source.mesh.elemFields
    if fault == "missing":
        params["fieldName"] = "absent"
    elif fault == "reserved":
        params["targetName"] = "flowgraph_node_id"
    elif fault == "dimension":
        params["dimensionality"] = 4
    elif fault == "shape":
        fields[field] = np.ones((len(fields[field]), 2, 2))
    elif fault == "dtype":
        fields[field] = fields[field].astype(str)
    else:
        fields[field] = np.ones(1)
    with pytest.raises(ValueError):
        run(node, source, params)


@pytest.mark.parametrize("entity,name", [("node", "temperature"), ("element", "pressure")])
def test_rename_remove_zero_copy(entity, name):
    source = fixture()
    original = source.mesh.nodeFields if entity == "node" else source.mesh.elemFields
    renamed = run(
        "rename-mesh-field", source, {"entity": entity, "fieldName": name, "newName": "renamed"}
    )["mesh"]
    fields = renamed.mesh.nodeFields if entity == "node" else renamed.mesh.elemFields
    assert name not in fields
    assert name in original
    assert np.shares_memory(fields["renamed"], original[name])
    assert not fields["renamed"].flags.writeable
    removed = run("remove-mesh-field", renamed, {"entity": entity, "fieldName": "renamed"})["mesh"]
    assert "renamed" not in (
        removed.mesh.nodeFields if entity == "node" else removed.mesh.elemFields
    )
    assert "renamed" in fields


@pytest.mark.parametrize(
    "node,params",
    [
        ("rename-mesh-field", {"fieldName": "temperature", "newName": "flowgraph_node_id"}),
        ("remove-mesh-field", {"fieldName": "flowgraph_node_id"}),
        ("rename-mesh-field", {"fieldName": "missing", "newName": "new"}),
        ("remove-mesh-field", {"fieldName": "missing"}),
        ("remove-mesh-field", {"entity": "bad", "fieldName": "temperature"}),
        ("rename-mesh-field", {"fieldName": "temperature", "newName": "other"}),
    ],
)
def test_field_edit_errors(node, params):
    source = fixture()
    source.mesh.nodeFields["other"] = np.zeros(5)
    with pytest.raises(ValueError):
        run(node, source, params)


@pytest.mark.parametrize("treatment,expected", [("all", [0]), ("any", [0, 1])])
def test_node_tags_to_element_tags(treatment, expected):
    source = fixture()
    result = run(
        "node-tags-to-element-tags",
        source,
        {"tags": ["boundary"], "treatment": treatment, "prefix": "from_"},
    )["mesh"].mesh
    np.testing.assert_array_equal(
        result.elements[ED.Triangle_3].tags["from_boundary"].GetIds(), expected
    )
    assert "from_boundary" not in source.mesh.elements[ED.Triangle_3].tags
    assert "boundary" in result.nodesTags
    assert not result.nodes.flags.writeable


def test_element_tags_to_node_tags():
    source = fixture()
    result = run("element-tags-to-node-tags", source)["mesh"].mesh
    np.testing.assert_array_equal(result.nodesTags["surface"].GetIds(), [0, 1, 2])
    assert "surface" not in source.mesh.nodesTags
    assert "surface" in result.elements[ED.Triangle_3].tags


@pytest.mark.parametrize(
    "node,tag",
    [("node-tags-to-element-tags", "boundary"), ("element-tags-to-node-tags", "surface")],
)
def test_tag_conversion_conflict_modes(node, tag):
    source = fixture()
    if node.startswith("node"):
        source.mesh.elements[ED.Triangle_3].tags.CreateTag(tag).SetIds([1])
    else:
        source.mesh.nodesTags.CreateTag(tag).SetIds([4])
    with pytest.raises(ValueError, match="already exists"):
        run(node, source)
    appended = run(node, source, {"mode": "append"})["mesh"].mesh
    replaced = run(node, source, {"mode": "replace"})["mesh"].mesh
    collection_a = (
        appended.elements[ED.Triangle_3].tags if node.startswith("node") else appended.nodesTags
    )
    collection_b = (
        replaced.elements[ED.Triangle_3].tags if node.startswith("node") else replaced.nodesTags
    )
    np.testing.assert_array_equal(
        collection_a[tag].GetIds(), [0, 1] if node.startswith("node") else [0, 1, 2, 4]
    )
    np.testing.assert_array_equal(
        collection_b[tag].GetIds(), [0] if node.startswith("node") else [0, 1, 2]
    )


@pytest.mark.parametrize("node", ["node-tags-to-element-tags", "element-tags-to-node-tags"])
@pytest.mark.parametrize(
    "params",
    [{"tags": ["missing"]}, {"tags": "bad"}, {"mode": "bad"}, {"dimensionality": 6}, {"prefix": 1}],
)
def test_tag_conversion_errors(node, params):
    with pytest.raises((ValueError, TypeError)):
        run(node, fixture(), params)


@pytest.mark.parametrize("selector_kind", ["node", "element"])
@pytest.mark.parametrize("entity", ["node", "element"])
def test_add_tag_selectors(selector_kind, entity):
    source = fixture()
    selector = (
        NodeFilter(nTag=["boundary"])
        if selector_kind == "node"
        else ElementFilter(eTag=["surface"])
    )
    result = run("add-tag", source, {"tagName": "added", "entity": entity}, filter=selector)[
        "mesh"
    ].mesh
    ids = (
        result.nodesTags["added"].GetIds()
        if entity == "node"
        else result.elements[ED.Triangle_3].tags["added"].GetIds()
    )
    np.testing.assert_array_equal(ids, [0, 1, 2] if entity == "node" else [0])
    assert "added" not in source.mesh.nodesTags
    assert "added" not in source.mesh.elements[ED.Triangle_3].tags


def test_add_tag_append_replace_and_any_node():
    source = fixture()
    selector = NodeFilter(nTag=["boundary"])
    result = run("add-tag", source, {"tagName": "surface", "treatment": "any"}, filter=selector)[
        "mesh"
    ]
    np.testing.assert_array_equal(
        result.mesh.elements[ED.Triangle_3].tags["surface"].GetIds(), [0, 1]
    )
    replaced = run("add-tag", result, {"tagName": "surface", "mode": "replace"}, filter=selector)[
        "mesh"
    ]
    np.testing.assert_array_equal(
        replaced.mesh.elements[ED.Triangle_3].tags["surface"].GetIds(), [0]
    )
    with pytest.raises(ValueError, match="already exists"):
        run("add-tag", source, {"tagName": "surface", "mode": "error"}, filter=selector)


def test_empty_conversions():
    source = MeshDocument(Mesh())
    source.mesh.nodeFields["empty"] = np.empty((0, 3))
    source.mesh.elemFields["empty"] = np.empty((0, 3))
    for node in ("nodal-to-element-field", "element-to-nodal-field"):
        assert run(node, source, {"fieldName": "empty", "targetName": "new"})["field"].shape == (
            0,
            3,
        )
    for node in ("node-tags-to-element-tags", "element-tags-to-node-tags"):
        assert run(node, source)["mesh"].mesh.GetNumberOfNodes() == 0


def test_merge_capacity_and_connected_roundtrip(tmp_path):
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            ADAPTERS.require("create-cube").create_instance("source"),
            ADAPTERS.require("merge-meshes").create_instance("merge"),
        ]
    )
    for slot in range(1, 129):
        graph.add_edge(WorkflowEdge("source", "mesh", "merge", f"mesh_{slot}"), registry)
    with pytest.raises(WorkflowValidationError):
        graph.add_edge(WorkflowEdge("source", "mesh", "merge", "mesh_129"), registry)
    path = tmp_path / "merge.json"
    save_workflow(graph, path)
    result = WorkflowExecutor(registry).run(load_workflow(path, registry))
    assert (
        result.node_outputs["merge"]["mesh"].mesh.GetNumberOfNodes()
        == 128 * result.node_outputs["source"]["mesh"].mesh.GetNumberOfNodes()
    )


def test_add_tag_replace_self_referencing_selector():
    source = fixture()
    result = run(
        "add-tag",
        source,
        {"tagName": "surface", "mode": "replace"},
        filter=ElementFilter(eTag=["surface"]),
    )["mesh"]
    np.testing.assert_array_equal(result.mesh.elements[ED.Triangle_3].tags["surface"].GetIds(), [0])
    result = run(
        "add-tag",
        source,
        {"tagName": "boundary", "entity": "node", "mode": "replace"},
        filter=NodeFilter(nTag=["boundary"]),
    )["mesh"]
    np.testing.assert_array_equal(result.mesh.nodesTags["boundary"].GetIds(), [0, 1, 2])


def test_bidirectional_conversion_connected_parameters(tmp_path):
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            ADAPTERS.require("create-cube").create_instance("mesh"),
            ADAPTERS.require("calculator").create_instance(
                "array", parameters={"formula": "np.arange(8.)"}
            ),
            ADAPTERS.require("set-mesh-field").create_instance(
                "attach", parameters={"fieldName": "temperature"}
            ),
            ADAPTERS.require("nodal-to-element-field").create_instance(
                "to_element", parameters={"fieldName": "wrong"}
            ),
            ADAPTERS.require("element-to-nodal-field").create_instance(
                "to_node", parameters={"fieldName": "temperature", "targetName": "averaged"}
            ),
            ADAPTERS.require("set-string").create_instance(
                "name", parameters={"value": "temperature"}
            ),
        ]
    )
    for edge in [
        WorkflowEdge("mesh", "mesh", "attach", "mesh"),
        WorkflowEdge("array", "result", "attach", "field"),
        WorkflowEdge("attach", "mesh", "to_element", "mesh"),
        WorkflowEdge("name", "value", "to_element", "fieldName"),
        WorkflowEdge("to_element", "mesh", "to_node", "mesh"),
    ]:
        graph.add_edge(edge, registry)
    path = tmp_path / "fields.json"
    save_workflow(graph, path)
    result = WorkflowExecutor(registry).run(load_workflow(path, registry))
    assert result.node_outputs["to_node"]["field"].shape == (8,)
    assert not result.node_outputs["to_node"]["field"].flags.writeable


def test_node_selector_connected_to_add_tag(tmp_path):
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            ADAPTERS.require("create-cube").create_instance("mesh"),
            ADAPTERS.require("create-muscat-node-filter").create_instance("selector"),
            ADAPTERS.require("add-tag").create_instance("tag", parameters={"tagName": "selected"}),
        ]
    )
    graph.add_edge(WorkflowEdge("mesh", "mesh", "tag", "mesh"), registry)
    graph.add_edge(WorkflowEdge("selector", "filter", "tag", "filter"), registry)
    path = tmp_path / "tag.json"
    save_workflow(graph, path)
    result = WorkflowExecutor(registry).run(load_workflow(path, registry))
    mesh = result.node_outputs["tag"]["mesh"].mesh
    assert sum(len(e.tags["selected"]) for e in mesh.elements) == mesh.GetNumberOfElements()


def test_structured_element_tags_survive_field_edits_and_conversion():
    source = MeshDocument(
        CreateConstantRectilinearMesh([2, 2, 2], [0.0, 0.0, 0.0], [1.0, 1.0, 1.0])
    )
    source.mesh.elements[ED.Hexahedron_8].tags.CreateTag("bulk").SetIds([0])
    source.mesh.nodeFields["value"] = np.ones(8)
    source.mesh.nodesTags.CreateTag("all").SetIds(np.arange(8))
    for node, params in [
        ("rename-mesh-field", {"fieldName": "value", "newName": "new"}),
        ("remove-mesh-field", {"fieldName": "value"}),
        ("nodal-to-element-field", {"fieldName": "value"}),
        ("node-tags-to-element-tags", {"tags": ["all"]}),
    ]:
        result = run(node, source, params)["mesh"].mesh
        np.testing.assert_array_equal(result.elements[ED.Hexahedron_8].tags["bulk"].GetIds(), [0])
    result = run("element-tags-to-node-tags", source, {"tags": ["bulk"]})["mesh"].mesh
    np.testing.assert_array_equal(result.nodesTags["bulk"].GetIds(), np.arange(8))
    assert "bulk" not in source.mesh.nodesTags


def test_tag_conversion_roundtrip_with_prefix_and_dimension():
    source = fixture()
    first = run(
        "node-tags-to-element-tags",
        source,
        {"tags": ["boundary"], "prefix": "e_", "dimensionality": 2},
    )["mesh"]
    second = run(
        "element-tags-to-node-tags",
        first,
        {"tags": ["e_boundary"], "prefix": "n_", "dimensionality": 2},
    )["mesh"]
    np.testing.assert_array_equal(second.mesh.nodesTags["n_e_boundary"].GetIds(), [0, 1, 2])
    empty = run(
        "element-tags-to-node-tags",
        source,
        {"tags": ["surface"], "prefix": "none_", "dimensionality": 3},
    )["mesh"]
    assert len(empty.mesh.nodesTags["none_surface"]) == 0


def test_merge_text_and_tensor_fields():
    first, second = fixture(), fixture()
    first.mesh.nodeFields["label"] = np.array(["abc"] * 5)
    second.mesh.nodeFields["label"] = np.array(["long label"] * 5)
    first.mesh.elemFields["tensor"] = np.arange(8).reshape(2, 2, 2)
    result = run("merge-meshes", mesh_1=first, mesh_2=second)["mesh"].mesh
    np.testing.assert_array_equal(result.nodeFields["label"], ["abc"] * 5 + ["long label"] * 5)
    np.testing.assert_array_equal(result.elemFields["tensor"][:2], first.mesh.elemFields["tensor"])
    np.testing.assert_array_equal(result.elemFields["tensor"][2:], 0)
