"""Priority-one mesh nodes preserve geometry, metadata, and upstream storage."""

import numpy as np
import pytest
from Muscat.MeshContainers import ElementsDescription as ED
from Muscat.MeshContainers.Filters.FilterObjects import ElementFilter
from Muscat.MeshContainers.Mesh import Mesh
from Muscat.MeshTools.MeshCreationTools import CreateCube, CreateSquare

from flowgraph.adapters import ADAPTERS
from flowgraph.adapters.filters import SELECTOR_OPERATORS
from flowgraph.adapters.mesh_analysis import MESH_NODES, SET_MESH_FIELD
from flowgraph.adapters.mesh_creation_tools import CREATE_CUBE_NODE
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import (
    WorkflowEdge,
    WorkflowExecutor,
    WorkflowGraph,
    WorkflowValidationError,
)
from flowgraph.application.workflow_io import load_workflow, save_workflow
from flowgraph.domain.mesh_document import MeshDocument


def run(node_id, mesh=None, parameters=None, **inputs):
    if mesh is not None:
        inputs["mesh"] = mesh
    return ADAPTERS.require(node_id).executor(inputs, parameters or {})


def cube():
    return MeshDocument(
        CreateCube(
            dimensions=[2, 2, 2], origin=[0.0, 0.0, 0.0], spacing=[1.0, 1.0, 1.0], ofTetras=True
        )
    )


def duplicates():
    mesh = Mesh()
    mesh.SetNodes(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 0.0]],
        generateOriginalIDs=True,
    )
    elements = mesh.GetElementsOfType(ED.Triangle_3)
    elements.AddNewElements(np.array([[0, 1, 2], [2, 1, 0], [3, 1, 2]]), np.array([10, 20, 30]))
    elements.tags.CreateTag("first").SetIds([0])
    elements.tags.CreateTag("last").SetIds([1, 2])
    mesh.nodesTags.CreateTag("duplicate").SetIds([3])
    mesh.nodeFields["temperature"] = np.array([10.0, 20.0, 30.0, 40.0])
    mesh.nodeFields["vector"] = np.arange(12.0).reshape(4, 3)
    mesh.elemFields["material"] = np.array([4, 5, 6])
    return MeshDocument(mesh)


@pytest.mark.parametrize("definition", (*MESH_NODES, SET_MESH_FIELD, *SELECTOR_OPERATORS))
def test_registration_and_roundtrip(definition, tmp_path):
    assert ADAPTERS.require(definition.id) is definition
    graph = WorkflowGraph([definition.create_instance("test")])
    path = tmp_path / "node.json"
    save_workflow(graph, path)
    restored = load_workflow(path, create_node_registry())
    assert restored.nodes[0].definition_id == definition.id


@pytest.mark.parametrize("entity", ["node", "element"])
@pytest.mark.parametrize("components", [1, 3])
def test_attach_field_zero_copy(entity, components):
    source = cube()
    count = (
        source.mesh.GetNumberOfNodes() if entity == "node" else source.mesh.GetNumberOfElements()
    )
    shape = (count,) if components == 1 else (count, components)
    data = np.arange(np.prod(shape), dtype=np.float32).reshape(shape)
    result = run("set-mesh-field", source, {"entity": entity, "fieldName": "new"}, field=data)[
        "mesh"
    ]
    fields = result.mesh.nodeFields if entity == "node" else result.mesh.elemFields
    assert np.shares_memory(fields["new"], data)
    assert not fields["new"].flags.writeable
    assert data.flags.writeable
    assert "new" not in source.mesh.nodeFields and "new" not in source.mesh.elemFields
    assert np.shares_memory(result.mesh.nodes, source.mesh.nodes)


@pytest.mark.parametrize(
    "parameters,data,message",
    [
        ({"fieldName": ""}, np.zeros(8), "nonempty"),
        ({"fieldName": "flowgraph_node_id"}, np.zeros(8), "reserved"),
        ({"fieldName": "flowgraph_element_id"}, np.zeros(8), "reserved"),
        ({"entity": "bad"}, np.zeros(8), "association"),
        ({}, np.zeros(7), "length"),
        ({}, np.zeros((8, 1, 1)), "1D or 2D"),
        ({}, np.array(1), "1D or 2D"),
    ],
)
def test_attach_field_errors(parameters, data, message):
    with pytest.raises(ValueError, match=message):
        run("set-mesh-field", cube(), parameters, field=data)


def test_skin_and_measurements():
    source = cube()
    source.mesh.nodeFields["temperature"] = np.arange(8.0)
    source.mesh.elemFields["material"] = np.ones(source.mesh.GetNumberOfElements())
    skin = run("extract-skin", source)["mesh"]
    assert skin.mesh.GetNumberOfElements() == 12
    assert skin.mesh.GetElementsDimensionality() == 2
    assert set(skin.mesh.elemFields) == {"flowgraph_element_id"}
    assert np.shares_memory(
        skin.mesh.nodeFields["temperature"], source.mesh.nodeFields["temperature"]
    )
    assert not skin.mesh.nodes.flags.writeable
    assert "material" in source.mesh.elemFields
    assert run("mesh-measure", source)["measure"] == pytest.approx(1.0)
    assert run("mesh-measure", skin)["measure"] == pytest.approx(6.0)
    measures = run("element-measures", source)
    assert not measures["measures"].flags.writeable
    assert not measures["indices"].flags.writeable
    assert measures["indices"].dtype.kind in "iu"
    assert measures["measures"].shape == (source.mesh.GetNumberOfElements(),)
    selector = ElementFilter(dimensionality=3)
    assert measures["measures"][
        np.concatenate([s.meshOffset + s.indices for s in selector(source.mesh)])
    ].sum() == pytest.approx(1.0)
    centers = run("element-centers", source)["centers"]
    expected = np.concatenate(
        [source.mesh.nodes[e.connectivity].mean(axis=1) for e in source.mesh.elements]
    )
    np.testing.assert_allclose(centers, expected)
    assert not centers.flags.writeable


def test_filtered_measure_alignment_and_mixed_dimension_error():
    source = cube()
    selected = source.mesh.GetElementsOfType(ED.Tetrahedron_4)
    selected.tags.CreateTag("chosen").SetIds([1, 3])
    selector = ElementFilter(eTag=["chosen"])
    filtered = run("element-measures", source, filter=selector)
    ids = np.concatenate([s.meshOffset + s.indices for s in selector(source.mesh)])
    np.testing.assert_array_equal(filtered["indices"], ids)
    np.testing.assert_allclose(
        filtered["measures"], run("element-measures", source)["measures"][ids]
    )
    assert run("mesh-measure", source, filter=selector)["measure"] == pytest.approx(
        filtered["measures"].sum()
    )
    with pytest.raises(ValueError, match="mixed-dimensional"):
        run("mesh-measure", source, filter=ElementFilter())
    empty = ElementFilter(eTag=["absent"])
    assert run("mesh-measure", source, filter=empty)["measure"] == 0.0
    assert run("element-measures", source, filter=empty)["indices"].size == 0


def test_merge_nodes_preserves_metadata_and_input():
    source = duplicates()
    result = run("merge-duplicate-nodes", source)
    mesh = result["mesh"].mesh
    np.testing.assert_array_equal(result["indices"], [0, 1, 2])
    np.testing.assert_array_equal(mesh.nodesTags["duplicate"].GetIds(), [0])
    np.testing.assert_array_equal(mesh.nodeFields["temperature"], [10, 20, 30])
    np.testing.assert_array_equal(mesh.nodeFields["flowgraph_node_id"], [0, 1, 2])
    np.testing.assert_array_equal(mesh.elements[ED.Triangle_3].connectivity[2], [0, 1, 2])
    np.testing.assert_array_equal(source.mesh.elements[ED.Triangle_3].connectivity[2], [3, 1, 2])
    assert source.mesh.GetNumberOfNodes() == 4
    assert not mesh.nodes.flags.writeable
    assert not mesh.nodeFields["vector"].flags.writeable
    assert not result["indices"].flags.writeable


def test_duplicate_elements_fields_tags_and_input():
    source = duplicates()
    mesh = run("remove-duplicate-elements", source)["mesh"].mesh
    assert mesh.GetNumberOfElements() == 2
    np.testing.assert_array_equal(mesh.elemFields["material"], [4, 6])
    np.testing.assert_array_equal(mesh.elemFields["flowgraph_element_id"], [0, 2])
    elements = mesh.elements[ED.Triangle_3]
    np.testing.assert_array_equal(elements.tags["first"].GetIds(), [0])
    np.testing.assert_array_equal(elements.tags["last"].GetIds(), [0, 1])
    assert source.mesh.GetNumberOfElements() == 3
    assert np.shares_memory(mesh.nodes, source.mesh.nodes)
    assert not elements.connectivity.flags.writeable


@pytest.mark.parametrize("tolerance", [-1.0, np.nan, np.inf, True])
def test_invalid_tolerance(tolerance):
    with pytest.raises(ValueError, match="Tolerance"):
        run("merge-duplicate-nodes", duplicates(), {"tolerance": tolerance})


def test_positive_tolerance():
    source = duplicates()
    source.mesh.nodes[3] += 1e-6
    assert run("merge-duplicate-nodes", source)["mesh"].mesh.GetNumberOfNodes() == 4
    assert (
        run("merge-duplicate-nodes", source, {"tolerance": 1e-4})["mesh"].mesh.GetNumberOfNodes()
        == 3
    )


def test_empty_mesh():
    source = MeshDocument(Mesh())
    assert run("mesh-measure", source)["measure"] == 0.0
    assert run("element-centers", source)["centers"].shape == (0, 3)
    assert run("element-measures", source)["indices"].size == 0
    for node in ("merge-duplicate-nodes", "remove-duplicate-elements"):
        assert run(node, source)["mesh"].mesh.GetNumberOfElements() == 0
    with pytest.raises(ValueError, match="dimension"):
        run("extract-skin", source)


def test_structured_mesh_cleanup_and_2d_skin():
    source = MeshDocument(CreateSquare(dimensions=[3, 3]))
    for node in ("merge-duplicate-nodes", "remove-duplicate-elements"):
        result = run(node, source)["mesh"].mesh
        assert result.GetNumberOfNodes() == source.mesh.GetNumberOfNodes()
        assert result.GetNumberOfElements() == source.mesh.GetNumberOfElements()
    assert run("extract-skin", source)["mesh"].mesh.GetElementsDimensionality() == 1


@pytest.mark.parametrize("dimension", [0, 4, True, 1.5])
def test_invalid_skin_dimension(dimension):
    with pytest.raises(ValueError, match="dimensionality"):
        run("extract-skin", cube(), {"dimensionality": dimension})


@pytest.mark.parametrize(
    "node,expected",
    [
        ("selector-union", [0, 1, 2]),
        ("selector-intersection", [1]),
        ("selector-difference", [0]),
        ("selector-complement", [2]),
    ],
)
def test_selector_set_operations(node, expected):
    source = duplicates()
    elements = source.mesh.elements[ED.Triangle_3]
    elements.tags.CreateTag("a").SetIds([0, 1])
    elements.tags.CreateTag("b").SetIds([1, 2])
    a, b = ElementFilter(eTag=["a"]), ElementFilter(eTag=["b"])
    inputs = {"filter_1": a, "filter_2": b}
    if node == "selector-difference":
        inputs = {"first": a, "second": b}
    elif node == "selector-complement":
        inputs = {"filter": a}
    selector = run(node, **inputs)["filter"]
    np.testing.assert_array_equal(selector.GetIdsToTreat(source.mesh, ED.Triangle_3), expected)


@pytest.mark.parametrize("node", ["selector-union", "selector-intersection"])
def test_selector_expansion_limit_and_empty(node):
    with pytest.raises(ValueError, match="At least one"):
        run(node)
    inputs = {f"filter_{i}": ElementFilter() for i in range(1, 129)}
    assert len(run(node, **inputs)["filter"].filters) == 128
    instance = ADAPTERS.require(node).create_instance("operator")
    assert instance is not None


def test_saved_connected_workflow(tmp_path):
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            CREATE_CUBE_NODE.create_instance("cube"),
            ADAPTERS.require("extract-skin").create_instance("skin"),
            ADAPTERS.require("mesh-measure").create_instance("measure"),
        ]
    )
    graph.add_edge(WorkflowEdge("cube", "mesh", "skin", "mesh"), registry)
    graph.add_edge(WorkflowEdge("skin", "mesh", "measure", "mesh"), registry)
    path = tmp_path / "workflow.json"
    save_workflow(graph, path)
    result = WorkflowExecutor(registry).run(load_workflow(path, registry))
    assert result.node_outputs["measure"]["measure"] > 0


def test_field_calculator_workflow(tmp_path):
    registry = create_node_registry()
    definitions = [
        CREATE_CUBE_NODE.create_instance("cube"),
        ADAPTERS.require("extract-field").create_instance(
            "extract", parameters={"fieldName": "flowgraph_node_id"}
        ),
        ADAPTERS.require("calculator").create_instance(
            "calc", parameters={"formula": "input_1 * 2"}
        ),
        SET_MESH_FIELD.create_instance("attach", parameters={"fieldName": "calculated"}),
    ]
    graph = WorkflowGraph(definitions)
    for edge in [
        WorkflowEdge("cube", "mesh", "extract", "mesh"),
        WorkflowEdge("cube", "mesh", "attach", "mesh"),
        WorkflowEdge("extract", "field", "calc", "input_1"),
        WorkflowEdge("calc", "result", "attach", "field"),
    ]:
        graph.add_edge(edge, registry)
    path = tmp_path / "calculate.json"
    save_workflow(graph, path)
    result = WorkflowExecutor(registry).run(load_workflow(path, registry))
    fields = result.node_outputs["attach"]["mesh"].mesh.nodeFields
    np.testing.assert_array_equal(fields["calculated"], fields["flowgraph_node_id"] * 2)
    assert not fields["calculated"].flags.writeable


@pytest.mark.parametrize("node_id", ["selector-union", "selector-intersection"])
def test_selector_graph_capacity_and_execution(node_id, tmp_path):
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            CREATE_CUBE_NODE.create_instance("cube"),
            ADAPTERS.require("create-muscat-element-filter").create_instance(
                "select", parameters={"dimensionality": [3]}
            ),
            ADAPTERS.require(node_id).create_instance("combine"),
            ADAPTERS.require("mesh-measure").create_instance("measure"),
        ]
    )
    for slot in range(1, 129):
        graph.add_edge(WorkflowEdge("select", "filter", "combine", f"filter_{slot}"), registry)
    with pytest.raises(WorkflowValidationError):
        graph.add_edge(WorkflowEdge("select", "filter", "combine", "filter_129"), registry)
    graph.add_edge(WorkflowEdge("cube", "mesh", "measure", "mesh"), registry)
    graph.add_edge(WorkflowEdge("combine", "filter", "measure", "filter"), registry)
    path = tmp_path / "select.json"
    save_workflow(graph, path)
    result = WorkflowExecutor(registry).run(load_workflow(path, registry))
    assert result.node_outputs["measure"]["measure"] > 0


def test_true_structured_container_cleanup():
    from Muscat.MeshTools.ConstantRectilinearMeshTools import CreateConstantRectilinearMesh

    mesh = CreateConstantRectilinearMesh([3, 3, 3], [0.0, 0.0, 0.0], [1.0, 1.0, 1.0])
    source = MeshDocument(mesh)
    for node in ("merge-duplicate-nodes", "remove-duplicate-elements"):
        result = run(node, source)["mesh"].mesh
        assert result.GetNumberOfElements() == 8
        assert result.GetNumberOfNodes() == 27
