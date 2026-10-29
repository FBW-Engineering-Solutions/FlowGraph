"""Session-local incremental execution; runtime objects never cross transports.

Pure computations are reusable by default; actions explicitly execute every
time. All executors must treat inputs as read-only, including nested objects.
Configuration is compared structurally; opaque runtime inputs are cache misses.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from flowgraph.application.file_dependencies import declared_dependency_metadata
from flowgraph.application.workflow_core import (
    NodeExecutionError,
    NodeRegistry,
    WorkflowExecutor,
    WorkflowGraph,
    WorkflowRunResult,
    WorkflowValidationError,
)
from flowgraph.domain.filepath import FilePath


def _token(value: Any) -> Any:
    """Snapshot supported configuration without retaining mutable aliases."""
    if value is None or type(value) in (str, bool, int):
        return (type(value).__name__, value)
    if type(value) is float:
        return ("float", value.hex())
    if isinstance(value, Path):
        return ("path", str(value))
    if isinstance(value, FilePath):
        return ("files", tuple(str(path) for path in value.files))
    if isinstance(value, Mapping) and all(isinstance(key, str) for key in value):
        return tuple((key, _token(item)) for key, item in sorted(value.items()))
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(_token(item) for item in value))
    # No repr(), object identity, or expensive array/mesh hashing as a substitute
    # for an explicit input revision. Unsupported inputs must never hit a cache.
    return object()


def _graph_token(graph: WorkflowGraph) -> Any:
    """Semantic child snapshot, deliberately excluding canvas positions."""
    return (
        tuple(
            (
                node.id,
                node.definition_id,
                _token(node.parameters),
                tuple(
                    (key, _graph_token(child)) for key, child in sorted(node.subworkflows.items())
                ),
            )
            for node in graph.nodes
        ),
        tuple(graph.edges),
        tuple(
            (p.name, p.node_id, p.node_port, p.data_type.id)
            for p in (*graph.inputs, *graph.outputs)
        ),
    )


@dataclass
class _Entry:
    signature: Any
    outputs: Mapping[str, Any]
    inputs: Mapping[str, Any]
    generation: int
    dependency_metadata: Any = None


_ACTIVE: ContextVar[tuple[WorkflowSession, str] | None] = ContextVar(
    "flowgraph_execution_session", default=None
)


def run_child(
    graph: WorkflowGraph,
    registry: NodeRegistry,
    *,
    key: str,
    initial_inputs: Mapping[str, Mapping[str, Any]],
    parallel_tasks: int = 1,
    gpu_available: bool = False,
) -> WorkflowRunResult:
    """Use an isolated child session when called during incremental execution."""
    active = _ACTIVE.get()
    if active is None:
        return WorkflowExecutor(
            registry, parallel_tasks=parallel_tasks, gpu_available=gpu_available
        ).run(graph, initial_inputs=initial_inputs)
    parent, node_id = active
    namespace = (node_id, key)
    if namespace not in parent.children:
        parent.children[namespace] = WorkflowSession(registry, max_entries=parent.max_entries)
    child = parent.children[namespace]
    parent.children.move_to_end(namespace)
    while len(parent.children) > parent.max_children:
        parent.children.popitem(last=False)[1].clear()
    return child.run(
        graph,
        initial_inputs=initial_inputs,
        from_scratch=parent._from_scratch or node_id in parent._forced,
        parallel_tasks=parallel_tasks,
        gpu_available=gpu_available,
    )


class WorkflowSession:
    """Own one workflow's bounded cache and authoritative execution metadata.

    Callers must serialize access to a session. Eviction is entry-count bounded,
    not a hard byte-memory limit; one mesh can itself be arbitrarily large.
    """

    def __init__(self, registry: NodeRegistry, *, max_entries: int = 256):
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self.registry = registry
        self.max_entries = max_entries
        self.max_children = 32
        self.epoch = uuid4().hex
        self.entries: OrderedDict[str, _Entry] = OrderedDict()
        self.children: OrderedDict[tuple[str, str], WorkflowSession] = OrderedDict()
        self._configuration: dict[str, Any] = {}
        self._generation = 0
        self._from_scratch = False
        self._forced: set[str] = set()
        self.metadata: dict[str, Any] = {}

    def clear(self) -> None:
        """Release retained objects, including child sessions, without deleting files."""
        self.entries.clear()
        self.children.clear()
        self._configuration.clear()
        self.epoch = uuid4().hex

    @staticmethod
    def _closure(roots: set[str], adjacency: Mapping[str, set[str]]) -> set[str]:
        result = set(roots)
        pending = list(roots)
        while pending:
            for candidate in adjacency.get(pending.pop(), ()):
                if candidate not in result:
                    result.add(candidate)
                    pending.append(candidate)
        return result

    def run(
        self,
        graph: WorkflowGraph,
        *,
        targets: set[str] | None = None,
        force: set[str] | None = None,
        from_scratch: bool = False,
        upstream: str = "normal",
        missing_only: bool = False,
        initial_inputs: Mapping[str, Mapping[str, Any]] | None = None,
        parallel_tasks: int = 1,
        gpu_available: bool = False,
    ) -> WorkflowRunResult:
        """Execute targets and missing dependencies, preserving independent results."""
        if upstream not in {"normal", "missing", "none"}:
            raise ValueError("upstream must be normal, missing, or none")
        issues = graph.validate(self.registry, require_complete=False)
        if issues:
            raise WorkflowValidationError(issues)
        order = graph.topological_order()
        all_ids = set(order)
        requested = all_ids if targets is None else set(targets)
        forced = set(force or ())
        if (requested | forced) - all_ids:
            raise KeyError(f"Unknown workflow nodes {sorted((requested | forced) - all_ids)!r}")
        predecessors = {node_id: set() for node_id in order}
        successors = {node_id: set() for node_id in order}
        for edge in graph.edges:
            predecessors[edge.target_node].add(edge.source_node)
            successors[edge.source_node].add(edge.target_node)
        dependency_scope = self._closure(requested, predecessors)
        scope = requested if upstream == "none" else dependency_scope
        if not forced <= scope:
            raise ValueError("Forced nodes must belong to the requested dependency scope")
        if from_scratch:
            self.clear()
        self._from_scratch, self._forced = from_scratch, forced
        injected = initial_inputs or {}
        configuration = {}
        for node in graph.nodes:
            definition = self.registry.require(node.definition_id)
            incoming = tuple(edge for edge in graph.edges if edge.target_node == node.id)
            supplied = {edge.target_port for edge in incoming} | set(injected.get(node.id, {}))
            parameter_ports = {
                port.name for port in definition.ports_for_instance(node) if port.is_param
            }
            parameters = {
                **definition.default_parameters,
                **node.parameters,
            }
            # Connected parameter values are execution-derived, not authored
            # settings. Their true dependencies are the edge/input tokens below.
            parameters = {
                key: value
                for key, value in parameters.items()
                if key not in supplied or key not in parameter_ports
            }
            configuration[node.id] = (
                id(definition),
                definition.cache_revision,
                _token(parameters),
                tuple(
                    (
                        e.source_node,
                        e.source_port,
                        e.target_port,
                        id(graph.edge_conversion(e, self.registry)),
                    )
                    for e in incoming
                ),
                tuple(
                    (p.name, p.direction.value, p.data_type.id, p.required)
                    for p in definition.ports_for_instance(node)
                ),
                frozenset(e.source_port for e in graph.edges if e.source_node == node.id)
                | frozenset(p.node_port for p in graph.outputs if p.node_id == node.id),
                _token(injected.get(node.id, {})),
                parallel_tasks,
                gpu_available,
                # Child sessions do their own fine-grained reconciliation. Parent
                # wrappers always execute so child side effects are never skipped.
                tuple(
                    (key, _graph_token(child)) for key, child in sorted(node.subworkflows.items())
                ),
            )
        changed = {
            key for key, value in configuration.items() if self._configuration.get(key) != value
        }
        invalid = self._closure(changed | forced, successors)
        # Outside-scope entries are last-completed results, not cache hits for
        # this request. Keep untouched branches visible. Their policies and
        # external dependencies are checked when they next enter execution scope;
        # configuration edits and upstream execution still invalidate.
        for node_id in set(self.entries) - all_ids | invalid:
            self.entries.pop(node_id, None)
        for namespace in list(self.children):
            if namespace[0] not in all_ids:
                self.children.pop(namespace).clear()
        self._configuration = configuration
        outputs = {key: entry.outputs for key, entry in self.entries.items()}
        inputs = {key: entry.inputs for key, entry in self.entries.items()}
        generations = {key: entry.generation for key, entry in self.entries.items()}
        executed: list[str] = []
        reused: list[str] = []
        failed: list[str] = []
        blocked: list[str] = []
        unstable_dependencies: set[str] = set()
        first_error: NodeExecutionError | None = None
        executor = WorkflowExecutor(
            self.registry, parallel_tasks=parallel_tasks, gpu_available=gpu_available
        )
        for node_id in order:
            if node_id not in dependency_scope:
                continue
            definition = self.registry.require(graph.require_node(node_id).definition_id)
            if any(source not in outputs for source in predecessors[node_id]):
                if node_id in scope:
                    blocked.append(node_id)
                    first_error = first_error or NodeExecutionError(
                        node_id,
                        definition.id,
                        "Required upstream results are missing or outdated; run upstream nodes first.",
                    )
                outputs.pop(node_id, None)
                inputs.pop(node_id, None)
                self.entries.pop(node_id, None)
                continue
            signature = (
                configuration[node_id],
                tuple((source, generations[source]) for source in sorted(predecessors[node_id])),
            )
            entry = self.entries.get(node_id)
            dependency_inputs = dict(injected.get(node_id, {}))
            dependency_parameters = {
                **definition.default_parameters,
                **graph.require_node(node_id).parameters,
            }
            dependency_token = None
            dependency_metadata = None
            if definition.cache_policy == "external" and definition.cache_dependencies:
                try:
                    for edge in graph.edges:
                        if edge.target_node == node_id:
                            value = outputs[edge.source_node][edge.source_port]
                            conversion = graph.edge_conversion(edge, self.registry)
                            dependency_inputs[edge.target_port] = (
                                conversion.convert(value) if conversion else value
                            )
                    dependency_metadata = declared_dependency_metadata(
                        definition.cache_dependencies, dependency_inputs, dependency_parameters
                    )
                    if (
                        entry
                        and dependency_metadata is not None
                        and dependency_metadata != entry.dependency_metadata
                    ):
                        # Metadata already proves invalidation. Hash only after executing
                        # to establish the new baseline, not before a known cache miss.
                        dependency_token = object()
                    else:
                        dependency_token = _token(
                            definition.cache_dependencies(dependency_inputs, dependency_parameters)
                        )
                except (OSError, ValueError, TypeError):
                    dependency_token = object()
            signature = (signature, dependency_token)
            if (
                (
                    definition.cache_policy in {"pure", "external"}
                    or missing_only
                    or (node_id not in requested and upstream != "normal")
                )
                and entry
                and entry.signature == signature
            ):
                reused.append(node_id)
                self.entries.move_to_end(node_id)
                continue
            if node_id not in scope:
                outdated = self._closure({node_id}, successors)
                invalid.update(outdated)
                for dependent in outdated:
                    self.entries.pop(dependent, None)
                    outputs.pop(dependent, None)
                    inputs.pop(dependent, None)
                continue
            # Remove stale outputs BEFORE execution, including on failure.
            self.entries.pop(node_id, None)
            outputs.pop(node_id, None)
            inputs.pop(node_id, None)
            active = _ACTIVE.set((self, node_id))
            instance = graph.require_node(node_id)
            authored_parameters = dict(instance.parameters)
            try:
                result = executor.run(
                    graph, node_ids={node_id}, initial_outputs=outputs, initial_inputs=injected
                )
            except NodeExecutionError as error:
                failed.append(node_id)
                first_error = first_error or error
                continue
            finally:
                # The low-level executor materializes parameter-port values on
                # the instance. Keep that legacy behavior stateless, but never
                # let a session overwrite the authored configuration.
                instance.parameters.clear()
                instance.parameters.update(authored_parameters)
                _ACTIVE.reset(active)
            executed.append(node_id)
            self._generation += 1
            generations[node_id] = self._generation
            outputs[node_id] = result.node_outputs[node_id]
            inputs[node_id] = result.node_inputs[node_id]
            self.entries[node_id] = _Entry(
                signature, outputs[node_id], inputs[node_id], self._generation, dependency_metadata
            )
            if definition.cache_policy == "external" and definition.cache_dependencies:
                try:
                    after = _token(
                        definition.cache_dependencies(dependency_inputs, dependency_parameters)
                    )
                except (OSError, ValueError, TypeError):
                    after = object()
                try:
                    after_metadata = declared_dependency_metadata(
                        definition.cache_dependencies, dependency_inputs, dependency_parameters
                    )
                except (OSError, ValueError, TypeError):
                    after_metadata = object()
                metadata_changed_before = (
                    entry is not None
                    and dependency_metadata is not None
                    and dependency_metadata != entry.dependency_metadata
                )
                if after_metadata != dependency_metadata or (
                    not metadata_changed_before and after != dependency_token
                ):
                    unstable_dependencies.update(self._closure({node_id}, successors))
                elif metadata_changed_before:
                    self.entries[node_id].signature = (signature[0], after)
            # Even a forced node outside another target's scope makes its old
            # downstream results stale immediately.
            for dependent in self._closure({node_id}, successors) - {node_id}:
                self.entries.pop(dependent, None)
                outputs.pop(dependent, None)
                inputs.pop(dependent, None)
        # Failure also invalidates outputs outside the selected scope.
        for dependent in self._closure(set(failed), successors):
            self.entries.pop(dependent, None)
            outputs.pop(dependent, None)
            inputs.pop(dependent, None)
        for node_id in unstable_dependencies:
            self.entries.pop(node_id, None)
        if unstable_dependencies:
            # External dependencies changed while executing; child results
            # derived from that unstable snapshot must not be reused either.
            self.children.clear()
        evicted = []
        while len(self.entries) > self.max_entries:
            evicted.append(self.entries.popitem(last=False)[0])
        self.metadata = {
            "epoch": self.epoch,
            "executed": executed,
            "reused": reused,
            "failed": failed,
            "blocked": blocked,
            "outside_scope": [key for key in order if key not in scope],
            "invalidated": sorted(invalid),
            "evicted": evicted,
            "retained_entries": len(self.entries),
        }
        completed = {key: value for key, value in outputs.items() if key in all_ids}
        result = WorkflowRunResult(
            tuple(executed), MappingProxyType(completed), MappingProxyType(inputs)
        )
        if first_error:
            first_error.partial_result = result
            raise first_error
        return result
