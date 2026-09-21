"""Shared helpers for tests."""

from flowgraph.adapters import ADAPTERS
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import WorkflowEdge, WorkflowGraph


def create_initial_workflow() -> WorkflowGraph:
    """Build the default typed ``file path -> Muscat loader`` test workflow."""
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
