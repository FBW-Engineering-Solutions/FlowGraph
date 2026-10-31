"""Muscat vector derivative accuracy, tensor layout and workflow contracts."""

import numpy as np
import pytest
from Muscat.MeshContainers import ElementsDescription as ED
from Muscat.MeshContainers.Filters.FilterObjects import ElementFilter
from Muscat.MeshTools.ConstantRectilinearMeshTools import CreateConstantRectilinearMesh
from Muscat.MeshTools.MeshCreationTools import CreateCube, CreateSquare

from flowgraph.adapters import ADAPTERS
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import WorkflowExecutor, WorkflowGraph
from flowgraph.application.workflow_io import load_workflow, save_workflow
from flowgraph.domain.mesh_document import MeshDocument


def run(mesh, entity="node", selector=None, **parameters):
    return ADAPTERS.require("vector-field-gradient").executor(
        {"mesh": MeshDocument(mesh), **({"filter": selector} if selector is not None else {})},
        {"fieldName": "velocity", "entity": entity, **parameters},
    )


@pytest.mark.parametrize("entity", ["node", "element"])
@pytest.mark.parametrize("components", [2, 3])
@pytest.mark.parametrize("tetrahedra", [False, True])
def test_linear_tensor_layout(entity, components, tetrahedra):
    mesh = CreateCube(dimensions=[3, 2, 2], ofTetras=tetrahedra)
    # Nonsymmetric, distinct derivatives detect swapped axes/transposition.
    jacobian = np.array([[2.0, 3.0, -4.0], [5.0, -6.0, 7.0], [-8.0, 9.0, 10.0]])[:components]
    mesh.nodeFields["velocity"] = mesh.nodes @ jacobian.T + np.arange(components)
    original = mesh.nodeFields["velocity"].copy()
    document = MeshDocument(mesh)
    result = run(mesh, entity)
    values = result["gradient"]
    expected = np.tile(jacobian.reshape(-1), (len(values), 1))
    if entity == "element":
        selection = np.concatenate(
            [s.meshOffset + s.indices for s in ElementFilter(dimensionality=3)(mesh)]
        )
        mask = np.ones(len(values), dtype=bool)
        mask[selection] = False
        expected[mask] = 0
    np.testing.assert_allclose(values, expected, atol=1e-11)
    output = result["mesh"].mesh
    fields = output.nodeFields if entity == "node" else output.elemFields
    assert values is fields["velocity_gradient"]
    assert not values.flags.writeable
    assert not output.nodes.flags.writeable
    assert np.shares_memory(output.nodes, mesh.nodes)
    assert np.shares_memory(output.nodeFields["velocity"], mesh.nodeFields["velocity"])
    np.testing.assert_array_equal(mesh.nodeFields["velocity"], original)
    assert "velocity_gradient" not in mesh.nodeFields
    assert "velocity_gradient" not in mesh.elemFields
    np.testing.assert_array_equal(
        output.nodeFields["flowgraph_node_id"], document.get_muscat_node_ids()
    )
    np.testing.assert_array_equal(
        output.elemFields["flowgraph_element_id"], document.get_muscat_elements_ids()
    )
    for elements in mesh.elements:
        for tag in elements.tags:
            np.testing.assert_array_equal(
                output.elements[elements.elementType].tags[tag.name].GetIds(), tag.GetIds()
            )
    # Flattened tensors can be projected through the existing VTK bridge.
    vtk = result["mesh"].to_vtk_unstructured_grid()
    data = vtk.GetPointData() if entity == "node" else vtk.GetCellData()
    assert data.GetArray("velocity_gradient").GetNumberOfComponents() == components * 3


@pytest.mark.parametrize("entity", ["node", "element"])
@pytest.mark.parametrize("dimension", [2, 3])
def test_plane_vector(entity, dimension):
    mesh = CreateSquare(dimensions=[3, 2], ofTriangles=True)
    if dimension == 3:
        mesh.nodes = np.column_stack([mesh.nodes, np.zeros(len(mesh.nodes))])
    jacobian = np.array([[2.0, 3.0, 0.0], [5.0, -6.0, 0.0]])[:, :dimension]
    mesh.nodeFields["velocity"] = mesh.nodes @ jacobian.T
    result = run(mesh, entity)["gradient"]
    if entity == "element":
        selection = next(ElementFilter(dimensionality=2)(mesh))
        result = result[selection.meshOffset + selection.indices]
    np.testing.assert_allclose(result, np.tile(jacobian.reshape(-1), (len(result), 1)), atol=1e-11)


@pytest.mark.parametrize("entity", ["node", "element"])
def test_selected_nonlinear_and_empty(entity):
    mesh = CreateCube(dimensions=[3, 2, 2], origin=[0.0, 0.0, 0.0])
    x, y, z = mesh.nodes.T
    mesh.nodeFields["velocity"] = np.column_stack([x**2, 3 * y, 4 * z])
    elements = mesh.elements[ED.Hexahedron_8]
    elements.tags.CreateTag("chosen").SetIds([1])
    selector = ElementFilter(eTag="chosen")
    result = run(mesh, entity, selector)["gradient"]
    indices = (
        elements.connectivity[1]
        if entity == "node"
        else next(selector(mesh)).meshOffset + np.array([1])
    )
    expected = np.diag([3.0, 3.0, 4.0]).reshape(-1)
    np.testing.assert_allclose(result[indices], np.tile(expected, (len(indices), 1)), atol=1e-11)
    np.testing.assert_array_equal(np.delete(result, indices, axis=0), 0)
    np.testing.assert_array_equal(
        run(mesh, entity, ElementFilter(elementType=[ED.Bar_3]))["gradient"], 0
    )


@pytest.mark.parametrize("entity", ["node", "element"])
def test_constant_and_structured_tags(entity):
    mesh = CreateConstantRectilinearMesh(
        dimensions=[3, 2, 2], origin=[0.0, 0.0, 0.0], spacing=[1.0, 1.0, 1.0]
    )
    mesh.elements[ED.Hexahedron_8].tags.CreateTag("chosen").SetIds([1])
    mesh.nodeFields["velocity"] = np.full((len(mesh.nodes), 3), 8, dtype=int)
    result = run(mesh, entity, ElementFilter(eTag="chosen"))
    np.testing.assert_allclose(result["gradient"], 0, atol=1e-11)
    np.testing.assert_array_equal(
        result["mesh"].mesh.elements[ED.Hexahedron_8].tags["chosen"].GetIds(), [1]
    )


@pytest.mark.parametrize(
    "bad",
    [
        np.ones(8),
        np.ones((8, 1)),
        np.ones((8, 4)),
        np.ones((7, 3)),
        np.ones((8, 3, 3)),
        np.ones((8, 3), dtype=bool),
        np.ones((8, 3), dtype=complex),
        np.full((8, 3), np.inf),
        np.full((8, 3), np.nan),
        np.full((8, 3), "x"),
    ],
)
def test_invalid_vector(bad):
    mesh = CreateCube()
    mesh.nodeFields["velocity"] = bad
    with pytest.raises(ValueError, match="finite real vector"):
        run(mesh)


def test_validation_and_overwrite():
    mesh = CreateCube()
    mesh.nodeFields["velocity"] = mesh.nodes.copy()
    for parameters, message in [
        ({"fieldName": "missing"}, "does not exist"),
        ({"fieldName": ""}, "nonempty"),
        ({"targetName": "flowgraph_element_id"}, "reserved"),
        ({"entity": "bad"}, "association"),
    ]:
        with pytest.raises(ValueError, match=message):
            run(mesh, **parameters)
    with pytest.raises(ValueError, match="single element dimension"):
        run(mesh, selector=ElementFilter())
    mesh.nodeFields["custom"] = np.zeros((8, 9))
    with pytest.raises(ValueError, match="already exists"):
        run(mesh, targetName="custom")
    output = run(mesh, targetName="custom", overwrite=True)
    np.testing.assert_allclose(
        output["gradient"], np.tile(np.eye(3).reshape(-1), (8, 1)), atol=1e-11
    )
    np.testing.assert_array_equal(mesh.nodeFields["custom"], 0)


@pytest.mark.parametrize("entity", ["node", "element"])
def test_persisted_execution(entity, tmp_path):
    definition = ADAPTERS.require("vector-field-gradient")
    instance = definition.create_instance("gradient")
    instance.parameters.update(fieldName="velocity", entity=entity)
    path = tmp_path / "vector.json"
    save_workflow(WorkflowGraph([instance]), path)
    registry = create_node_registry()
    graph = load_workflow(path, registry)
    mesh = CreateCube()
    mesh.nodeFields["velocity"] = mesh.nodes.copy()
    result = WorkflowExecutor(registry).run(
        graph, initial_inputs={"gradient": {"mesh": MeshDocument(mesh)}}
    )
    values = result.node_outputs["gradient"]["gradient"]
    assert values.shape[1] == 9
    assert not values.flags.writeable
