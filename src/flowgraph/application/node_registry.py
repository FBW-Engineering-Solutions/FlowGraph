"""Headless built-in workflow node catalog and starter graph."""

from flowgraph.adapters import ADAPTERS
from flowgraph.application.workflow_core import NodeRegistry, WorkflowEdge, WorkflowGraph

__all__ = ["create_initial_workflow", "create_node_registry"]


def create_node_registry() -> NodeRegistry:
    """Return all built-in nodes whose executors are safe for headless use."""
    registry = NodeRegistry()
    for definition in ADAPTERS.node_definitions:
        registry.register(definition)
    return registry


def create_initial_workflow() -> WorkflowGraph:
    """Build the default typed ``file path -> Muscat loader`` workflow fixture."""
    select_file = ADAPTERS.require("select-file")
    load_muscat = ADAPTERS.require("load-muscat")
    graph = WorkflowGraph(
        nodes=[
            select_file.create_instance("file-path", x=30, y=120),
            load_muscat.create_instance("load-muscat", x=320, y=120),
        ]
    )
    graph.add_edge(
        WorkflowEdge("file-path", "path", "load-muscat", "path"),
        create_node_registry(),
    )
    return graph
