"""Implicit geometry catalog, runtime behavior, and connected filtering."""

import inspect

import numpy as np
import pytest
from Muscat.ImplicitGeometry import ImplicitGeometryObjects, ImplicitGeometryOperators
from Muscat.ImplicitGeometry.ImplicitGeometryBase import ImplicitGeometryBase
from Muscat.MeshTools.MeshCreationTools import CreateCube

from flowgraph.adapters import ADAPTERS
from flowgraph.adapters.data_types import MUSCAT_ZONE
from flowgraph.adapters.filters import CREATE_MUSCAT_ELEMENT_FILTER, FILTER_MESH_WITH_MUSCAT
from flowgraph.adapters.mesh_creation_tools import CREATE_CUBE_NODE
from flowgraph.adapters.zones import AVAILABLE_NODES
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import WorkflowEdge, WorkflowExecutor, WorkflowGraph
from flowgraph.application.workflow_io import load_workflow, save_workflow
from flowgraph.application.workflow_web_catalog import workflow_web_catalog
from flowgraph.domain.mesh_document import MeshDocument


def node(name):
    return ADAPTERS.require(f"zone-{name}")


def test_all_concrete_objects_and_operators_have_one_node() -> None:
    classes = {
        name.lower().removeprefix("implicitgeometry")
        for module in (ImplicitGeometryObjects, ImplicitGeometryOperators)
        for name, cls in inspect.getmembers(module, inspect.isclass)
        if cls.__module__ == module.__name__ and issubclass(cls, ImplicitGeometryBase)
    }
    assert {definition.id.removeprefix("zone-") for definition in AVAILABLE_NODES} == classes
    assert len(AVAILABLE_NODES) == 24
    assert all(definition.output("zone").data_type is MUSCAT_ZONE for definition in AVAILABLE_NODES)


def test_zones_catalog_is_nested_under_mesh_filters_and_json_serializable() -> None:
    catalog = workflow_web_catalog()
    mesh = next(group for group in catalog["groups"] if group["label"] == "Mesh Tools")
    filters = next(group for group in mesh["subgroups"] if group["label"] == "Filters")
    zones = next(group for group in filters["subgroups"] if group["label"] == "Zones")
    assert [entry["id"] for entry in zones["nodes"]] == [d.id for d in AVAILABLE_NODES]
    assert node("analytical").requirements == ("py:muscat", "py:sympy")
    assert node("union").input("zone").expandable == 128


def test_all_zone_configuration_defaults_round_trip(tmp_path) -> None:
    registry = create_node_registry()
    graph = WorkflowGraph(
        [definition.create_instance(definition.id) for definition in AVAILABLE_NODES]
    )
    path = tmp_path / "all-zones.json"
    save_workflow(graph, path)
    restored = load_workflow(path, registry)
    assert [instance.definition_id for instance in restored.nodes] == [
        definition.id for definition in AVAILABLE_NODES
    ]


def test_expandable_union_connected_inputs_execute_and_round_trip(tmp_path) -> None:
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            node("sphere").create_instance("first"),
            node("sphere").create_instance("second", parameters={"center": [2.0, 0.0, 0.0]}),
            node("union").create_instance("union"),
        ]
    )
    for index, source in enumerate(("first", "second"), 1):
        graph.add_edge(WorkflowEdge(source, "zone", "union", f"zone_{index}"), registry)
    path = tmp_path / "union.json"
    save_workflow(graph, path)
    result = WorkflowExecutor(registry).run(load_workflow(path, registry))
    zone = result.node_outputs["union"]["zone"]
    np.testing.assert_allclose(zone(np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]])), [-1.0, -1.0])


@pytest.mark.parametrize("definition", AVAILABLE_NODES, ids=lambda definition: definition.id)
def test_each_zone_constructs_and_evaluates_with_real_muscat(definition, tmp_path) -> None:
    mesh = CreateCube(dimensions=[3, 3, 3], spacing=[0.5, 0.5, 0.5], ofTetras=True)
    mesh.nodesTags.CreateTag("centers").SetIds([0])
    for elements in mesh.elements:
        if elements.GetDimensionality() == 3:
            centers = mesh.nodes[elements.connectivity].mean(axis=1)
            elements.tags.CreateTag("selected").SetIds(np.flatnonzero(centers[:, 0] < -0.5))
    sphere = node("sphere").executor({}, {})["zone"]
    points = np.array([[0.1, 0.2, 0.3], [2.0, 2.0, 2.0]])
    parameters = {p.name: p.default for p in definition.parameters}
    inputs = {
        "mesh": MeshDocument(mesh),
        "zone": sphere,
        "zone1": sphere,
        "zone2": node("sphere").executor({}, {"radius": 0.5})["zone"],
        "zone_1": sphere,
        "zone_2": sphere,
    }
    if definition.id == "zone-wrapped":
        parameters["field"] = [-1.0, 1.0]
    if definition.id == "zone-spherefromntag":
        parameters["nTag"] = "centers"
    if definition.id in ("zone-byetag", "zone-byetagii"):
        parameters["etags"] = ["selected"]
    if definition.id == "zone-stl":
        from Muscat.IO.StlWriter import WriteMeshToStl
        from Muscat.MeshTools.MeshModificationTools import ComputeSkin

        path = tmp_path / "surface.stl"
        WriteMeshToStl(str(path), ComputeSkin(mesh, inPlace=False))
        parameters["filename"] = str(path)
    zone = definition.executor(inputs, parameters)["zone"]
    assert type(zone).__name__.lower() == "implicitgeometry" + definition.id.removeprefix("zone-")
    if definition.id == "zone-byetagii":
        # This Muscat class is a support-node field, not a pointwise distance.
        points = mesh.nodes
    values = zone(points)
    assert values.shape == (len(points),)
    assert np.all(np.isfinite(values))


@pytest.mark.parametrize(
    "name,parameters,expected",
    [
        ("sphere", {}, [-1.0, 1.0]),
        ("ellipse", {"radius": [2.0, 1.0, 1.0]}, [-1.0, 0.0]),
        ("plane", {"normal": [2.0, 0.0, 0.0]}, [0.0, 2.0]),
        ("axisalignbox", {}, [0.0, 1.0]),
    ],
)
def test_geometry_signed_distances(name, parameters, expected) -> None:
    zone = node(name).executor({}, parameters)["zone"]
    np.testing.assert_allclose(zone(np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]])), expected)


@pytest.mark.parametrize(
    "name,parameters",
    [
        ("sphere", {"radius": -1.0}),
        ("sphere", {"center": [0.0, 0.0]}),
        ("plane", {"normal": [0.0, 0.0, 0.0]}),
        ("cylinder", {"center2": [0.0, 0.0, 0.0]}),
        ("axisalignbox", {"size": [1.0, 0.0, 1.0]}),
        ("union", {}),
        ("intersection", {}),
        ("wrapped", {"field": []}),
    ],
)
def test_invalid_geometry_fails_clearly(name, parameters) -> None:
    with pytest.raises(ValueError):
        node(name).executor({}, parameters)


@pytest.mark.parametrize(
    "name,parameters,expected",
    [
        ("union", {}, [-1.0, 1.0]),
        ("intersection", {}, [-0.5, 1.5]),
        ("difference", {}, [0.5, 1.0]),
        ("offset", {"offset": 0.25}, [-0.75, 1.25]),
        ("insideout", {}, [1.0, -1.0]),
        ("shell", {"thickness": 0.2}, [1.0, 0.8]),
        ("transform", {"offset": [1.0, 0.0, 0.0]}, [0.0, 2.0]),
    ],
)
def test_operator_signed_distances_without_mutating_sources(name, parameters, expected) -> None:
    sphere = node("sphere").executor({}, {})["zone"]
    inner = node("sphere").executor({}, {"radius": 0.5})["zone"]
    inputs = {"zone": sphere, "zone1": sphere, "zone2": inner, "zone_1": sphere, "zone_2": inner}
    points = np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
    zone = node(name).executor(inputs, parameters)["zone"]
    np.testing.assert_allclose(zone(points), expected)
    np.testing.assert_allclose(sphere(points), [-1.0, 1.0])


def test_connected_zone_operator_selector_and_filter_round_trip(tmp_path) -> None:
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            CREATE_CUBE_NODE.create_instance("mesh", parameters={"dimensions": [3, 3, 3]}),
            node("plane").create_instance("plane", parameters={"offset": 0.5}),
            node("insideout").create_instance("invert"),
            CREATE_MUSCAT_ELEMENT_FILTER.create_instance(
                "selector", parameters={"dimensionality": [3]}
            ),
            FILTER_MESH_WITH_MUSCAT.create_instance("filtered"),
        ]
    )
    for edge in (
        WorkflowEdge("plane", "zone", "invert", "zone"),
        WorkflowEdge("invert", "zone", "selector", "zone_1"),
        WorkflowEdge("mesh", "mesh", "filtered", "mesh"),
        WorkflowEdge("selector", "filter", "filtered", "filter"),
    ):
        graph.add_edge(edge, registry)
    path = tmp_path / "zones.json"
    save_workflow(graph, path)
    restored = load_workflow(path, registry)
    result = WorkflowExecutor(registry).run(restored)
    selected = result.node_outputs["filtered"]["mesh"].mesh
    source = result.node_outputs["mesh"]["mesh"].mesh
    assert 0 < selected.GetNumberOfElements() < source.GetNumberOfElements()


@pytest.mark.parametrize(
    "treatment,expected", [("CENTER", 4), ("ALL_NODES", 0), ("AT_LEAST_ONE", 4)]
)
def test_element_selector_zone_treatment(treatment, expected) -> None:
    mesh = CreateCube(dimensions=[3, 3, 3], origin=[0.0, 0.0, 0.0], spacing=[0.5, 0.5, 0.5])
    zone = node("plane").executor({}, {"offset": 0.3})["zone"]
    selector = CREATE_MUSCAT_ELEMENT_FILTER.executor(
        {"zone_1": zone}, {"zonesTreatment": treatment, "dimensionality": [3]}
    )["filter"]
    assert sum(len(selection.indices) for selection in selector(mesh)) == expected
