"""Numerical and workflow contracts for Muscat-backed scalar derivatives."""

import numpy as np
import pytest
from Muscat.MeshContainers import ElementsDescription as ED
from Muscat.MeshContainers.Filters.FilterObjects import ElementFilter
from Muscat.MeshTools.ConstantRectilinearMeshTools import CreateConstantRectilinearMesh
from Muscat.MeshTools.MeshCreationTools import (
    CreateCube,
    CreateSquare,
    CreateUniformMeshOfBars,
    ToQuadraticMesh,
)

from flowgraph.adapters import ADAPTERS
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import WorkflowEdge, WorkflowExecutor, WorkflowGraph
from flowgraph.application.workflow_io import load_workflow, save_workflow
from flowgraph.domain.mesh_document import MeshDocument


def run(mesh, entity="node", **parameters):
    selector = parameters.pop("filter", None)
    return ADAPTERS.require("scalar-field-gradient").executor(
        {"mesh": MeshDocument(mesh), **({"filter": selector} if selector is not None else {})},
        {"fieldName": "temperature", "entity": entity, **parameters},
    )


@pytest.mark.parametrize("entity", ["node", "element"])
@pytest.mark.parametrize("tetrahedra", [False, True])
@pytest.mark.parametrize("column", [False, True])
def test_linear_field(entity, tetrahedra, column):
    mesh = CreateCube(dimensions=[3, 2, 2], ofTetras=tetrahedra)
    mesh.nodeFields["temperature"] = mesh.nodes @ [2.0, -3.0, 4.0] + 7
    if column:
        mesh.nodeFields["temperature"] = mesh.nodeFields["temperature"][:, None]
    original = mesh.nodeFields["temperature"].copy()
    result = run(mesh, entity)
    values = result["gradient"]
    selected = np.concatenate(
        [s.meshOffset + s.indices for s in ElementFilter(dimensionality=3)(mesh)]
    )
    if entity == "node":
        np.testing.assert_allclose(values, np.tile([2, -3, 4], (len(mesh.nodes), 1)), atol=1e-12)
    else:
        np.testing.assert_allclose(
            values[selected], np.tile([2, -3, 4], (len(selected), 1)), atol=1e-12
        )
        np.testing.assert_array_equal(np.delete(values, selected, axis=0), 0)
    output = result["mesh"].mesh
    fields = output.nodeFields if entity == "node" else output.elemFields
    assert fields["temperature_gradient"] is values
    assert not values.flags.writeable
    assert np.shares_memory(output.nodes, mesh.nodes)
    assert np.shares_memory(output.nodeFields["temperature"], mesh.nodeFields["temperature"])
    assert not output.nodes.flags.writeable
    assert "temperature_gradient" not in mesh.nodeFields
    assert "temperature_gradient" not in mesh.elemFields
    np.testing.assert_array_equal(mesh.nodeFields["temperature"], original)
    for source in mesh.elements:
        for tag in source.tags:
            np.testing.assert_array_equal(
                output.elements[source.elementType].tags[tag.name].GetIds(), tag.GetIds()
            )


@pytest.mark.parametrize("entity", ["node", "element"])
def test_constant_field(entity):
    mesh = CreateSquare(dimensions=[3, 3], ofTriangles=True)
    mesh.nodeFields["temperature"] = np.full(len(mesh.nodes), 9, dtype=int)
    np.testing.assert_allclose(run(mesh, entity)["gradient"], 0, atol=1e-12)


@pytest.mark.parametrize("entity", ["node", "element"])
def test_selection_and_empty(entity):
    mesh = CreateCube(dimensions=[3, 2, 2])
    mesh.nodeFields["temperature"] = mesh.nodes @ [2.0, 3.0, 4.0]
    elements = mesh.elements[ED.Hexahedron_8]
    elements.tags.CreateTag("chosen").SetIds([1])
    selector = ElementFilter(eTag="chosen")
    result = run(mesh, entity, filter=selector)["gradient"]
    indices = (
        elements.connectivity[1]
        if entity == "node"
        else next(selector(mesh)).meshOffset + np.array([1])
    )
    np.testing.assert_allclose(result[indices], np.tile([2, 3, 4], (len(indices), 1)), atol=1e-12)
    np.testing.assert_array_equal(np.delete(result, indices, axis=0), 0)
    # A valid filter with no matching element types yields full-sized zeros.
    np.testing.assert_array_equal(
        run(mesh, entity, filter=ElementFilter(elementType=[ED.Bar_3]))["gradient"], 0
    )


def test_nonlinear_field_cell_locality_and_nodal_recovery():
    mesh = CreateCube(dimensions=[3, 2, 2], origin=[0.0, 0.0, 0.0])
    mesh.nodeFields["temperature"] = mesh.nodes[:, 0] ** 2
    cells = run(mesh, "element")["gradient"]
    indices = next(ElementFilter(dimensionality=3)(mesh)).meshOffset + np.arange(2)
    np.testing.assert_allclose(cells[indices], [[1, 0, 0], [3, 0, 0]], atol=1e-12)
    nodes = run(mesh)["gradient"]
    np.testing.assert_allclose(nodes[:, 0], mesh.nodes[:, 0] + 1, atol=1e-12)
    np.testing.assert_allclose(nodes[:, 1:], 0, atol=1e-12)


@pytest.mark.parametrize("entity", ["node", "element"])
def test_structured_mesh_tags(entity):
    mesh = CreateConstantRectilinearMesh(
        dimensions=[3, 2, 2], origin=[0.0, 0.0, 0.0], spacing=[1.0, 1.0, 1.0]
    )
    mesh.nodeFields["temperature"] = mesh.nodes @ [1.0, 2.0, 3.0]
    mesh.elements[ED.Hexahedron_8].tags.CreateTag("chosen").SetIds([1])
    result = run(mesh, entity, filter=ElementFilter(eTag="chosen"))
    np.testing.assert_array_equal(
        result["mesh"].mesh.elements[ED.Hexahedron_8].tags["chosen"].GetIds(), [1]
    )
    assert np.any(result["gradient"])


@pytest.mark.parametrize(
    "bad",
    [
        np.ones((8, 3)),
        np.ones((7,)),
        np.ones((8, 1, 1)),
        np.ones(8, dtype=bool),
        np.ones(8, dtype=complex),
        np.array([np.nan] * 8),
        np.array(["a"] * 8),
    ],
)
def test_invalid_scalar(bad):
    mesh = CreateCube(dimensions=[2, 2, 2])
    mesh.nodeFields["temperature"] = bad
    with pytest.raises(ValueError, match="finite real scalar"):
        run(mesh)


def test_names_collisions_and_selection_validation():
    mesh = CreateCube(dimensions=[2, 2, 2])
    mesh.nodeFields["temperature"] = mesh.nodes[:, 0]
    with pytest.raises(ValueError, match="does not exist"):
        run(mesh, fieldName="missing")
    with pytest.raises(ValueError, match="association"):
        run(mesh, entity="bad")
    with pytest.raises(ValueError, match="reserved"):
        run(mesh, targetName="flowgraph_node_id")
    with pytest.raises(ValueError, match="single element dimension"):
        run(mesh, filter=ElementFilter())
    mesh.nodeFields["custom"] = np.zeros((8, 3))
    with pytest.raises(ValueError, match="already exists"):
        run(mesh, targetName="custom")
    result = run(mesh, targetName="custom", overwrite=True)
    np.testing.assert_allclose(result["gradient"][:, 0], 1)
    np.testing.assert_array_equal(mesh.nodeFields["custom"], 0)


def test_registration_and_persistence(tmp_path):
    definition = ADAPTERS.require("scalar-field-gradient")
    instance = definition.create_instance("gradient")
    instance.parameters.update(fieldName="temperature", entity="element")
    path = tmp_path / "gradient.json"
    save_workflow(WorkflowGraph([instance]), path)
    loaded = load_workflow(path, create_node_registry()).nodes[0]
    assert loaded.parameters["entity"] == "element"
    assert loaded.parameters["fieldName"] == "temperature"


@pytest.mark.parametrize("entity", ["node", "element"])
def test_embedded_surface_gradient(entity):
    mesh = CreateSquare(dimensions=[3, 2], ofTriangles=True)
    mesh.nodes = np.column_stack((mesh.nodes, np.zeros(len(mesh.nodes))))
    mesh.nodeFields["temperature"] = mesh.nodes @ np.array([2.0, -3.0, 0.0])
    result = run(mesh, entity)["gradient"]
    if entity == "element":
        selection = next(ElementFilter(dimensionality=2)(mesh))
        result = result[selection.meshOffset + selection.indices]
    np.testing.assert_allclose(result, np.tile([2, -3, 0], (len(result), 1)), atol=1e-12)


def test_connected_workflow(tmp_path):
    registry = create_node_registry()
    source = ADAPTERS.require("create-cube").create_instance("source")
    ids = ADAPTERS.require("extract-field").create_instance("ids")
    ids.parameters.update(entity="node", fieldName="flowgraph_node_id")
    gradient = ADAPTERS.require("scalar-field-gradient").create_instance("gradient")
    gradient.parameters.update(fieldName="index", entity="element")
    attach = ADAPTERS.require("set-mesh-field").create_instance("attach")
    attach.parameters.update(fieldName="index", entity="node")
    selector = ADAPTERS.require("create-muscat-element-filter").create_instance("selector")
    selector.parameters["dimensionality"] = [3]
    graph = WorkflowGraph([source, ids, attach, selector, gradient])
    for edge in [
        WorkflowEdge("source", "mesh", "ids", "mesh"),
        WorkflowEdge("source", "mesh", "attach", "mesh"),
        WorkflowEdge("ids", "field", "attach", "field"),
        WorkflowEdge("attach", "mesh", "gradient", "mesh"),
    ]:
        graph.add_edge(edge, registry)
    # Filter source uses the shared selector port, not a bespoke gradient selector.
    output_port = ADAPTERS.require("create-muscat-element-filter").outputs[0].name
    graph.add_edge(WorkflowEdge("selector", output_port, "gradient", "filter"), registry)
    path = tmp_path / "connected.json"
    save_workflow(graph, path)
    result = WorkflowExecutor(registry).run(load_workflow(path, registry))
    assert result.node_outputs["gradient"]["gradient"].shape[1] == 3
    assert not result.node_outputs["gradient"]["gradient"].flags.writeable


@pytest.mark.parametrize("entity", ["node", "element"])
@pytest.mark.parametrize("kind", ["bar", "quadratic"])
def test_additional_element_spaces(entity, kind):
    mesh = (
        CreateUniformMeshOfBars(0.0, 2.0, 3)
        if kind == "bar"
        else ToQuadraticMesh(CreateSquare(ofTriangles=True))
    )
    mesh.nodeFields["temperature"] = 2 * mesh.nodes[:, 0] + 1
    result = run(mesh, entity)["gradient"]
    if entity == "element":
        indices = np.concatenate(
            [
                s.meshOffset + s.indices
                for s in ElementFilter(dimensionality=mesh.GetElementsDimensionality())(mesh)
            ]
        )
        result = result[indices]
    expected = np.zeros_like(result)
    expected[:, 0] = 2
    np.testing.assert_allclose(result, expected, atol=1e-10)
