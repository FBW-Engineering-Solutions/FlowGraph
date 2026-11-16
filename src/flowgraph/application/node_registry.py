"""Headless built-in and explicitly configured plugin node registries."""

from collections.abc import Sequence
from pathlib import Path

from flowgraph.adapters import ADAPTERS, AdapterGroup
from flowgraph.application.plugins import PluginError, load_plugin_groups
from flowgraph.application.workflow_core import NodeRegistry

__all__ = ["create_node_registry"]


def create_node_registry(
    *,
    plugins: Sequence[str | Path] = (),
    extra_groups: tuple[AdapterGroup, ...] = (),
) -> NodeRegistry:
    """Return built-ins plus explicitly configured, trusted plugin definitions."""
    registry = NodeRegistry()
    for definition in ADAPTERS.node_definitions:
        registry.register(definition)
    for group in (*extra_groups, *load_plugin_groups(plugins)):
        for definition in group.all_node_definitions():
            try:
                registry.register(definition)
            except ValueError as error:
                raise PluginError(f"{group.label}: {error}") from error
    return registry
