"""Compatibility exports for headless workflow composition."""

from __future__ import annotations

from flowgraph.application.node_registry import create_initial_workflow, create_node_registry

__all__ = [
    "create_initial_workflow",
    "create_node_registry",
]
