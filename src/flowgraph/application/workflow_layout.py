"""Deterministic layout helpers for directed workflow graphs."""

from __future__ import annotations

from collections import defaultdict

from flowgraph.application.workflow_core import WorkflowGraph

WORKFLOW_LAYER_SPACING = 360.0
"""Horizontal distance between successive dependency layers in pixels."""

WORKFLOW_NODE_SPACING = 180.0
"""Vertical distance between nodes in one dependency layer in pixels."""


def organize_workflow_nodes(
    workflow: WorkflowGraph,
    *,
    layer_spacing: float = WORKFLOW_LAYER_SPACING,
    node_spacing: float = WORKFLOW_NODE_SPACING,
) -> dict[str, tuple[float, float]]:
    """Return stable left-to-right positions for every node in a workflow.

    Nodes occupy a layer one greater than the deepest upstream dependency. The
    layout explicitly detects crossing edges and deterministically swaps pairs
    of nodes in one layer when a permutation reduces the total crossing count.
    Every layer starts at the same vertical origin, producing a regular grid.

    Parameters
    ----------
    workflow:
        Authoritative workflow graph to arrange.
    layer_spacing:
        Horizontal distance in pixels between dependency layers.
    node_spacing:
        Vertical distance in pixels between sibling nodes.

    Returns
    -------
    dict[str, tuple[float, float]]
        Positions keyed by node ID. An empty graph produces an empty mapping.
    """
    if layer_spacing <= 0 or node_spacing <= 0:
        raise ValueError("Workflow layout spacing must be positive")

    node_ids = sorted(node.id for node in workflow.nodes)
    predecessors: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    successors: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    for edge in workflow.edges:
        predecessors[edge.target_node].add(edge.source_node)
        successors[edge.source_node].add(edge.target_node)

    remaining_predecessors = {node_id: set(values) for node_id, values in predecessors.items()}
    ready = sorted(node_id for node_id, values in remaining_predecessors.items() if not values)
    layers: dict[str, int] = {node_id: 0 for node_id in ready}
    ordered_node_ids: list[str] = []
    while ready:
        node_id = ready.pop(0)
        ordered_node_ids.append(node_id)
        for successor_id in sorted(successors[node_id]):
            layers[successor_id] = max(layers.get(successor_id, 0), layers[node_id] + 1)
            remaining_predecessors[successor_id].discard(node_id)
            if not remaining_predecessors[successor_id]:
                ready.append(successor_id)
        ready.sort()

    if len(ordered_node_ids) != len(node_ids):
        raise ValueError("Workflow layout requires an acyclic graph")

    nodes_by_layer: dict[int, list[str]] = defaultdict(list)
    for node_id in ordered_node_ids:
        nodes_by_layer[layers[node_id]].append(node_id)

    for layer_node_ids in nodes_by_layer.values():
        layer_node_ids.sort()
    _reduce_edge_crossings(nodes_by_layer, workflow)

    positions: dict[str, tuple[float, float]] = {}
    for layer, layer_node_ids in nodes_by_layer.items():
        for index, node_id in enumerate(layer_node_ids):
            positions[node_id] = (layer * layer_spacing, index * node_spacing)
    return positions


def _reduce_edge_crossings(
    nodes_by_layer: dict[int, list[str]],
    workflow: WorkflowGraph,
) -> None:
    """Swap layer-node pairs whenever the permutation reduces edge crossings."""
    if len(nodes_by_layer) < 2:
        return
    crossing_count = _crossing_count(nodes_by_layer, workflow)
    improved = True
    while improved:
        improved = False
        for layer in sorted(nodes_by_layer):
            node_ids = nodes_by_layer[layer]
            for first_index in range(len(node_ids) - 1):
                for second_index in range(first_index + 1, len(node_ids)):
                    node_ids[first_index], node_ids[second_index] = (
                        node_ids[second_index],
                        node_ids[first_index],
                    )
                    candidate_count = _crossing_count(nodes_by_layer, workflow)
                    if candidate_count < crossing_count:
                        crossing_count = candidate_count
                        improved = True
                        break
                    node_ids[first_index], node_ids[second_index] = (
                        node_ids[second_index],
                        node_ids[first_index],
                    )
                if improved:
                    break
            if improved:
                break


def _crossing_count(nodes_by_layer: dict[int, list[str]], workflow: WorkflowGraph) -> int:
    """Return the number of geometric crossings among the workflow's directed edges."""
    positions = {
        node_id: (float(layer), float(index))
        for layer, node_ids in nodes_by_layer.items()
        for index, node_id in enumerate(node_ids)
    }
    crossings = 0
    for first_index, first_edge in enumerate(workflow.edges):
        for second_edge in workflow.edges[first_index + 1 :]:
            if {
                first_edge.source_node,
                first_edge.target_node,
            }.intersection((second_edge.source_node, second_edge.target_node)):
                continue
            if _edges_cross(
                first_edge.source_node,
                first_edge.target_node,
                second_edge.source_node,
                second_edge.target_node,
                positions,
            ):
                crossings += 1
    return crossings


def _edges_cross(
    first_source: str,
    first_target: str,
    second_source: str,
    second_target: str,
    positions: dict[str, tuple[float, float]],
) -> bool:
    """Return whether two directed edge segments strictly intersect on the canvas."""
    first_start, first_end = positions[first_source], positions[first_target]
    second_start, second_end = positions[second_source], positions[second_target]
    overlap_start = max(first_start[0], second_start[0])
    overlap_end = min(first_end[0], second_end[0])
    if overlap_start >= overlap_end:
        return False
    first_difference_at_start = _edge_y(first_start, first_end, overlap_start) - _edge_y(
        second_start, second_end, overlap_start
    )
    first_difference_at_end = _edge_y(first_start, first_end, overlap_end) - _edge_y(
        second_start, second_end, overlap_end
    )
    return first_difference_at_start * first_difference_at_end < 0


def _edge_y(start: tuple[float, float], end: tuple[float, float], x: float) -> float:
    """Return the vertical coordinate for a point on an edge at horizontal coordinate ``x``."""
    return start[1] + (end[1] - start[1]) * (x - start[0]) / (end[0] - start[0])
