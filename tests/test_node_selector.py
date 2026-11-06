"""Typed node and element selector composition with real Muscat filters."""

import numpy as np
import pytest
from Muscat.MeshContainers import ElementsDescription as ED
from Muscat.MeshContainers.Filters.FilterObjects import ElementFilter, NodeFilter
from Muscat.MeshContainers.Mesh import Mesh

from flowgraph.adapters import ADAPTERS
from flowgraph.adapters.data_types import MUSCAT_ELEMENT_FILTER, MUSCAT_NODE_FILTER
from flowgraph.adapters.filters import CREATE_MUSCAT_ELEMENT_FILTER, CREATE_MUSCAT_NODE_FILTER
from flowgraph.adapters.zones import AVAILABLE_NODES
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.port_conversions import resolve_port_conversion
from flowgraph.application.workflow_core import (
    WorkflowEdge,
    WorkflowExecutor,
    WorkflowGraph,
    WorkflowValidationError,
)
from flowgraph.application.workflow_io import load_workflow, save_workflow
from flowgraph.application.workflow_web_catalog import workflow_web_catalog


@pytest.fixture
def mesh():
    mesh = Mesh()
    mesh.SetNodes([[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0]], generateOriginalIDs=True)
    bars = mesh.GetElementsOfType(ED.ElementType.Bar_2)
    bars.AddNewElements(np.array([[0, 1], [1, 2], [2, 3]]))
    bars.tags.CreateTag("first").SetIds([0])
    bars.tags.CreateTag("last").SetIds([2])
    mesh.nodesTags.CreateTag("middle").SetIds([1, 2])
    mesh.nodesTags.CreateTag("left").SetIds([0, 1])
    return mesh


def test_node_selector_registration_and_distinct_port_types():
    assert ADAPTERS.require("create-muscat-node-filter") is CREATE_MUSCAT_NODE_FILTER
    mesh_tools = next(group for group in ADAPTERS.groups if group.label == "Mesh Tools")
    filters = next(group for group in mesh_tools.subgroups if group.label == "Filters")
    assert CREATE_MUSCAT_NODE_FILTER in filters.node_definitions
    for definition in (CREATE_MUSCAT_NODE_FILTER, CREATE_MUSCAT_ELEMENT_FILTER):
        assert definition.input("nFilter").data_type is MUSCAT_NODE_FILTER
        assert definition.input("eFilter").data_type is MUSCAT_ELEMENT_FILTER
        assert not definition.input("nFilter").required
        assert not definition.input("eFilter").required
    assert CREATE_MUSCAT_NODE_FILTER.output("filter").data_type is MUSCAT_NODE_FILTER
    assert not MUSCAT_ELEMENT_FILTER.accepts(NodeFilter())
    assert MUSCAT_NODE_FILTER.accepts(ElementFilter())


def test_element_filter_supports_node_filter_interface_without_copying():
    conversion = resolve_port_conversion(MUSCAT_ELEMENT_FILTER, MUSCAT_NODE_FILTER)
    assert conversion is not None
    selector = ElementFilter(eTag="first")
    assert conversion.convert(selector) is selector
    assert resolve_port_conversion(MUSCAT_NODE_FILTER, MUSCAT_ELEMENT_FILTER) is None


@pytest.mark.parametrize("target", [CREATE_MUSCAT_NODE_FILTER, CREATE_MUSCAT_ELEMENT_FILTER])
def test_element_filter_connects_to_node_filter_port_round_trip(tmp_path, mesh, target):
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            CREATE_MUSCAT_ELEMENT_FILTER.create_instance("source", parameters={"etag": ["first"]}),
            target.create_instance("target"),
        ]
    )
    graph.add_edge(WorkflowEdge("source", "filter", "target", "nFilter"), registry)
    path = tmp_path / "element-as-node-filter.json"
    save_workflow(graph, path)
    result = WorkflowExecutor(registry).run(load_workflow(path, registry))
    source = result.node_outputs["source"]["filter"]
    assert result.node_inputs["target"]["nFilter"] is source
    selector = result.node_outputs["target"]["filter"]
    assert selector.nFilter is source
    if target is CREATE_MUSCAT_NODE_FILTER:
        np.testing.assert_array_equal(selector.GetNodesIndices(mesh), [0, 1])
    else:
        np.testing.assert_array_equal(selector.GetGlobalIds(mesh), [0])


def test_node_filter_cannot_connect_to_element_only_port():
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            CREATE_MUSCAT_NODE_FILTER.create_instance("source"),
            CREATE_MUSCAT_ELEMENT_FILTER.create_instance("target"),
        ]
    )
    with pytest.raises(WorkflowValidationError):
        graph.add_edge(WorkflowEdge("source", "filter", "target", "eFilter"), registry)


def test_selector_catalog_exports_typed_optional_nested_connectors():
    conversions = workflow_web_catalog()["conversions"]
    assert any(
        conversion["source_type_id"] == "filter-like"
        and conversion["target_type_id"] == "node-filter-like"
        for conversion in conversions
    )
    assert not any(
        conversion["source_type_id"] == "node-filter-like"
        and conversion["target_type_id"] == "filter-like"
        for conversion in conversions
    )
    mesh = next(
        group for group in workflow_web_catalog()["groups"] if group["label"] == "Mesh Tools"
    )
    filters = next(group for group in mesh["subgroups"] if group["label"] == "Filters")
    nodes = {node["id"]: node for node in filters["nodes"]}
    for definition in (CREATE_MUSCAT_NODE_FILTER, CREATE_MUSCAT_ELEMENT_FILTER):
        ports = {
            port["name"]: port
            for port in nodes[definition.id]["ports"]
            if port["direction"] == "input"
        }
        assert ports["nFilter"]["data_type_id"] == "node-filter-like"
        assert ports["eFilter"]["data_type_id"] == "filter-like"
        assert not ports["nFilter"]["required"] and not ports["eFilter"]["required"]


def test_node_selector_multiple_zones_are_combined_with_or(mesh):
    plane = next(node for node in AVAILABLE_NODES if node.id == "zone-plane")
    left = plane.executor({}, {"offset": 0.5})["zone"]
    right = plane.executor({}, {"normal": [-1.0, 0.0, 0.0], "offset": -2.5})["zone"]
    selector = CREATE_MUSCAT_NODE_FILTER.executor({"zone_1": left, "zone_2": right}, {})["filter"]
    np.testing.assert_array_equal(selector.GetNodesIndices(mesh), [0, 3])


@pytest.mark.parametrize(
    "parameters,expected",
    [
        ({}, [0, 1, 2, 3]),
        ({"ntag": ["middle"]}, [1, 2]),
        ({"etag": ["first"]}, [0, 1]),
        ({"ntag": ["middle"], "etag": ["first"]}, [1]),
    ],
)
def test_node_selector_tags(mesh, parameters, expected):
    selector = CREATE_MUSCAT_NODE_FILTER.executor({}, parameters)["filter"]
    assert isinstance(selector, NodeFilter)
    np.testing.assert_array_equal(selector.GetNodesIndices(mesh), expected)


def test_node_selector_intersects_zones_and_both_nested_filters(mesh):
    plane = next(node for node in AVAILABLE_NODES if node.id == "zone-plane")
    zone = plane.executor({}, {"offset": 1.5})["zone"]
    nfilter = NodeFilter(nTag="middle")
    efilter = ElementFilter(eTag="first")
    selector = CREATE_MUSCAT_NODE_FILTER.executor(
        {"zone_1": zone, "nFilter": nfilter, "eFilter": efilter}, {}
    )["filter"]
    assert selector.nFilter is nfilter and selector.eFilter is efilter
    np.testing.assert_array_equal(selector.GetNodesIndices(mesh), [1])
    np.testing.assert_array_equal(nfilter.GetNodesIndices(mesh), [1, 2])


def test_nested_node_filter_is_applied_not_just_stored(mesh):
    inner = CREATE_MUSCAT_NODE_FILTER.executor({}, {"ntag": ["middle"]})["filter"]
    outer = CREATE_MUSCAT_NODE_FILTER.executor({"nFilter": inner}, {"ntag": ["left"]})["filter"]
    np.testing.assert_array_equal(outer.GetNodesIndices(mesh), [1])


@pytest.mark.parametrize("treatment,expected", [("ALL_NODES", [0]), ("AT_LEAST_ONE", [0, 1])])
def test_element_selector_uses_nested_node_filter_treatment(mesh, treatment, expected):
    selector = CREATE_MUSCAT_ELEMENT_FILTER.executor(
        {"nFilter": NodeFilter(nTag="left")}, {"nFilterTreatment": treatment}
    )["filter"]
    np.testing.assert_array_equal(selector.GetGlobalIds(mesh), expected)


def test_element_selector_intersects_both_nested_filters(mesh):
    selector = CREATE_MUSCAT_ELEMENT_FILTER.executor(
        {"nFilter": NodeFilter(nTag="left"), "eFilter": ElementFilter(eTag="last")},
        {"nFilterTreatment": "AT_LEAST_ONE"},
    )["filter"]
    np.testing.assert_array_equal(selector.GetGlobalIds(mesh), [])


@pytest.mark.parametrize("parameters", [{"ntag": "middle"}, {"etag": [1]}])
def test_node_selector_validates_tag_lists(parameters):
    with pytest.raises(TypeError):
        CREATE_MUSCAT_NODE_FILTER.executor({}, parameters)


def test_all_four_nested_connector_combinations_round_trip_and_execute(tmp_path, mesh):
    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            CREATE_MUSCAT_NODE_FILTER.create_instance("nodes", parameters={"ntag": ["middle"]}),
            CREATE_MUSCAT_ELEMENT_FILTER.create_instance(
                "elements", parameters={"etag": ["first"]}
            ),
            CREATE_MUSCAT_NODE_FILTER.create_instance("composed-nodes"),
            CREATE_MUSCAT_ELEMENT_FILTER.create_instance(
                "composed-elements",
                parameters={
                    "nFilterTreatment": "AT_LEAST_ONE",
                },
            ),
        ]
    )
    for target in ("composed-nodes", "composed-elements"):
        graph.add_edge(WorkflowEdge("nodes", "filter", target, "nFilter"), registry)
        graph.add_edge(WorkflowEdge("elements", "filter", target, "eFilter"), registry)
    path = tmp_path / "selectors.json"
    save_workflow(graph, path)
    result = WorkflowExecutor(registry).run(load_workflow(path, registry))
    np.testing.assert_array_equal(
        result.node_outputs["composed-nodes"]["filter"].GetNodesIndices(mesh), [1]
    )
    np.testing.assert_array_equal(
        result.node_outputs["composed-elements"]["filter"].GetGlobalIds(mesh), [0]
    )
