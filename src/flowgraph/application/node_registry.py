"""Headless built-in workflow node catalog and starter graph."""

from flowgraph.adapters import ADAPTERS
from flowgraph.application.workflow_core import NodeRegistry

__all__ = ["create_node_registry"]


def create_node_registry() -> NodeRegistry:
    """Return all built-in nodes whose executors are safe for headless use."""
    registry = NodeRegistry()
    for definition in ADAPTERS.node_definitions:
        registry.register(definition)
    return registry
