"""Typed, UI-independent workflow graph validation and execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field, replace
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Generic, TypeVar, get_args, get_origin

if TYPE_CHECKING:
    from flowgraph.application.port_conversions import PortConversion

T = TypeVar("T")
NodeExecutor = Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any] | None]
PortResolver = Callable[[Mapping[str, Any]], tuple["PortDefinition", ...]]
InstancePortResolver = Callable[["NodeInstance"], tuple["PortDefinition", ...]]
InstanceExecutor = Callable[
    ["NodeInstance", Mapping[str, Any], Mapping[str, Any], "NodeRegistry"], Mapping[str, Any] | None
]
SubworkflowFactory = Callable[[], "WorkflowGraph"]
WorkflowExecutorFunction = Callable[
    [Mapping[str, Any], Mapping[str, Any] | None], Mapping[str, Any]
]


@dataclass(frozen=True)
class DataType(Generic[T]):
    """Stable workflow type identity paired with a runtime Python type."""

    id: str
    label: str
    python_type: type[T] | tuple[type[Any], ...]

    def accepts(self, value: object) -> bool:
        """Return whether *value* satisfies this workflow type at runtime."""
        origin = get_origin(self.python_type)
        if origin is not None:
            if isinstance(value, origin):
                if origin == list:
                    args = get_args(self.python_type)
                    for v in value:
                        if not isinstance(v, args):
                            return False
                    return True
            else:
                return False
        return isinstance(value, self.python_type)

    def is_compatible_with(self, target: DataType[Any]) -> bool:
        """Use stable type identity; conversions require an explicit node."""
        if self.python_type is object or target.python_type is object:
            return True
        return self.python_type == target.python_type


class PortDirection(str, Enum):
    INPUT = "input"
    OUTPUT = "output"


@dataclass(frozen=True)
class ParameterOption:
    """One serializable choice offered by a parameter editor."""

    value: str | int | float
    label: str


@dataclass(frozen=True)
class ParameterDefinition:
    """Serializable configuration contract declared alongside a workflow node."""

    name: str
    kind: DataType[Any]
    label: str
    default: Any
    placeholder: str = ""
    options: tuple[ParameterOption, ...] = ()
    file_patterns: tuple[str, ...] = ()
    port: bool = True  # if this param must be export as a port


@dataclass(frozen=True)
class PortDefinition:
    """A named, typed endpoint on a node or workflow definition.

    ``accepted_data_types`` adds explicit alternatives for inputs that support
    more than one wire type. The declared ``data_type`` remains the primary
    type shown by existing clients and used for output validation.
    """

    name: str
    direction: PortDirection
    data_type: DataType[Any]
    label: str | None = None
    required: bool = True
    is_param: bool = False
    accepted_data_types: tuple[DataType[Any], ...] = ()

    @property
    def display_label(self) -> str:
        return self.label or self.name

    @property
    def accepted_types(self) -> tuple[DataType[Any], ...]:
        """Return the primary type followed by explicitly accepted alternatives."""
        return (self.data_type, *self.accepted_data_types)

    def accepts(self, value: object) -> bool:
        """Return whether this port accepts a runtime input value."""
        return any(data_type.accepts(value) for data_type in self.accepted_types)

    def accepts_type(self, source: DataType[Any]) -> bool:
        """Return whether this input port accepts a source port's type directly."""
        return any(source.is_compatible_with(data_type) for data_type in self.accepted_types)


@dataclass(frozen=True)
class WorkflowPort:
    """A public workflow port mapped to a port on one node instance."""

    name: str
    node_id: str
    node_port: str
    direction: PortDirection
    data_type: DataType[Any]
    label: str | None = None
    is_param: bool = False

    @property
    def display_label(self) -> str:
        return self.label or self.name


@dataclass(frozen=True)
class NodeDefinition:
    """Reusable behavior and port contract for a kind of workflow node."""

    id: str
    icon: str
    label: str
    ports: tuple[PortDefinition, ...]
    executor: NodeExecutor
    description: str = ""
    parameters: tuple[ParameterDefinition, ...] = ()
    default_parameters: Mapping[str, Any] = field(default_factory=dict)
    presentation: str = "standard"
    port_resolver: PortResolver | None = None
    instance_port_resolver: InstancePortResolver | None = None
    instance_executor: InstanceExecutor | None = None
    subworkflow_factory: SubworkflowFactory | None = None
    color: str | None = None

    def __post_init__(self) -> None:

        # add paramters as ports
        parameter_ports = tuple(
            PortDefinition(
                p.name, PortDirection.INPUT, p.kind, p.label, required=False, is_param=True
            )
            for p in self.parameters
            if p.port
        )

        object.__setattr__(
            self,
            "ports",
            self.ports + parameter_ports,
        )

        names = [(port.direction, port.name) for port in self.ports]
        if len(names) != len(set(names)):
            raise ValueError(f"Node definition {self.id!r} has duplicate port names")
        parameter_names = [parameter.name for parameter in self.parameters]
        if len(parameter_names) != len(set(parameter_names)):
            raise ValueError(f"Node definition {self.id!r} has duplicate parameters")
        schema_defaults = {
            parameter.name: deepcopy(parameter.default) for parameter in self.parameters
        }
        if (
            self.parameters
            and self.default_parameters
            and schema_defaults != dict(self.default_parameters)
        ):
            raise ValueError(
                f"Node definition {self.id!r} parameter defaults do not match its schema"
            )
        if self.parameters and not self.default_parameters:
            object.__setattr__(self, "default_parameters", schema_defaults)

    def ports_for(self, parameters: Mapping[str, Any] | None = None) -> tuple[PortDefinition, ...]:
        """Return this node's static ports plus any instance-specific ports."""
        if self.port_resolver is None:
            return self.ports
        return self.port_resolver(parameters or {})

    def ports_for_instance(self, instance: NodeInstance) -> tuple[PortDefinition, ...]:
        """Return ports resolved from an individual configured node instance."""
        if self.instance_port_resolver is not None:
            return self.instance_port_resolver(instance)
        return self.ports_for(instance.parameters)

    @staticmethod
    def _inputs(ports: tuple[PortDefinition, ...]) -> tuple[PortDefinition, ...]:
        return tuple(port for port in ports if port.direction is PortDirection.INPUT)

    @staticmethod
    def _outputs(ports: tuple[PortDefinition, ...]) -> tuple[PortDefinition, ...]:
        return tuple(port for port in ports if port.direction is PortDirection.OUTPUT)

    @property
    def inputs(self) -> tuple[PortDefinition, ...]:
        return self._inputs(self.ports)

    @property
    def outputs(self) -> tuple[PortDefinition, ...]:
        return self._outputs(self.ports)

    def input(
        self, name: str, parameters: Mapping[str, Any] | None = None
    ) -> PortDefinition | None:
        return next(
            (port for port in self._inputs(self.ports_for(parameters)) if port.name == name), None
        )

    def output(
        self, name: str, parameters: Mapping[str, Any] | None = None
    ) -> PortDefinition | None:
        return next(
            (port for port in self._outputs(self.ports_for(parameters)) if port.name == name), None
        )

    def input_for_instance(self, name: str, instance: NodeInstance) -> PortDefinition | None:
        """Return one input port resolved from an individual node instance."""
        return next(
            (port for port in self._inputs(self.ports_for_instance(instance)) if port.name == name),
            None,
        )

    def output_for_instance(self, name: str, instance: NodeInstance) -> PortDefinition | None:
        """Return one output port resolved from an individual node instance."""
        return next(
            (
                port
                for port in self._outputs(self.ports_for_instance(instance))
                if port.name == name
            ),
            None,
        )

    def execute_instance(
        self,
        instance: NodeInstance,
        inputs: Mapping[str, Any],
        registry: NodeRegistry,
    ) -> Mapping[str, Any] | None:
        """Execute one instance through its specialized or regular executor."""
        parameters = MappingProxyType(instance.parameters)
        if self.instance_executor is not None:
            return self.instance_executor(instance, inputs, parameters, registry)
        return self.executor(inputs, parameters)

    def create_instance(
        self,
        instance_id: str,
        *,
        parameters: Mapping[str, Any] | None = None,
        x: float = 0,
        y: float = 0,
    ) -> NodeInstance:
        """Create an independently configured instance of this definition."""
        configured_parameters = deepcopy(dict(self.default_parameters))
        if parameters is not None:
            configured_parameters.update(deepcopy(dict(parameters)))
        return NodeInstance(
            id=instance_id,
            definition_id=self.id,
            parameters=configured_parameters,
            x=x,
            y=y,
            subworkflow=None if self.subworkflow_factory is None else self.subworkflow_factory(),
        )

    def create_icon_arguments(self) -> dict[str, str]:
        """Return toolbar button arguments that add this registered node type."""
        return {
            "icon": self.icon,
            "variant": "text",
            "size": "small",
            "title": self.label,
            "click": f"trigger('AddNode', [{self.id!r}])",
        }


@dataclass
class NodeInstance:
    """A configured and positioned occurrence of a registered node definition."""

    id: str
    definition_id: str
    parameters: dict[str, Any] = field(default_factory=dict)
    x: float = 0
    y: float = 0
    subworkflow: WorkflowGraph | None = None

    def pprint(self):
        print(f"{self.id}")
        print(f"  type: {self.definition_id}")
        for k, v in self.parameters.items():
            print(f"  {k}:{v}")


@dataclass(frozen=True)
class WorkflowEdge:
    """A directed connection between one named output and one named input."""

    source_node: str
    source_port: str
    target_node: str
    target_port: str

    @property
    def id(self) -> str:
        return f"{self.source_node}({self.source_port})->{self.target_node}({self.target_port})"


class ValidationCode(str, Enum):
    UNKNOWN_DEFINITION = "unknown_definition"
    UNKNOWN_NODE = "unknown_node"
    UNKNOWN_SOURCE_PORT = "unknown_source_port"
    UNKNOWN_TARGET_PORT = "unknown_target_port"
    TYPE_MISMATCH = "type_mismatch"
    DUPLICATE_EDGE = "duplicate_edge"
    INPUT_ALREADY_CONNECTED = "input_already_connected"
    MISSING_REQUIRED_INPUT = "missing_required_input"
    CYCLE = "cycle"
    EXPORTED_INPUT_CONNECTED = "exported_input_connected"
    INVALID_EXPORTED_PORT = "invalid_exported_port"


@dataclass(frozen=True)
class ValidationIssue:
    code: ValidationCode
    message: str
    node_id: str | None = None
    edge_id: str | None = None


class WorkflowError(Exception):
    """Base error for invalid graphs and failed workflow runs."""


class WorkflowValidationError(WorkflowError):
    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))


class NodeExecutionError(WorkflowError):
    def __init__(
        self,
        node_id: str,
        definition_id: str,
        message: str,
        partial_result: WorkflowRunResult | None = None,
    ) -> None:
        self.node_id = node_id
        self.definition_id = definition_id
        self.partial_result = partial_result
        super().__init__(f"Node {node_id!r} ({definition_id!r}) failed: {message}")


class NodeRegistry:
    """Registry of node definitions available to workflow graphs."""

    def __init__(self) -> None:
        self._definitions: dict[str, NodeDefinition] = {}

    def register(self, definition: NodeDefinition) -> None:
        if definition.id in self._definitions:
            raise ValueError(f"Node definition {definition.id!r} is already registered")
        self._definitions[definition.id] = definition

    def get(self, definition_id: str) -> NodeDefinition | None:
        return self._definitions.get(definition_id)

    def require(self, definition_id: str) -> NodeDefinition:
        definition = self.get(definition_id)
        if definition is None:
            raise KeyError(f"Unknown node definition {definition_id!r}")
        return definition

    def create_instance(
        self,
        definition_id: str,
        instance_id: str,
        *,
        parameters: Mapping[str, Any] | None = None,
        x: float = 0,
        y: float = 0,
    ) -> NodeInstance:
        """Create an instance through its registered definition."""
        return self.require(definition_id).create_instance(
            instance_id,
            parameters=parameters,
            x=x,
            y=y,
        )

    @property
    def definitions(self) -> Mapping[str, NodeDefinition]:
        return MappingProxyType(self._definitions)


class WorkflowGraph:
    """Authoritative mutable workflow structure."""

    def __init__(
        self,
        nodes: tuple[NodeInstance, ...] | list[NodeInstance] = (),
        edges: tuple[WorkflowEdge, ...] | list[WorkflowEdge] = (),
        inputs: tuple[WorkflowPort, ...] | list[WorkflowPort] = (),
        outputs: tuple[WorkflowPort, ...] | list[WorkflowPort] = (),
    ) -> None:
        self._nodes: dict[str, NodeInstance] = {}
        self._edges: list[WorkflowEdge] = []
        self._inputs: dict[str, WorkflowPort] = {}
        self._outputs: dict[str, WorkflowPort] = {}
        for node in nodes:
            self.add_node(node)
        for edge in edges:
            self._edges.append(edge)
        self._inputs = {port.name: port for port in inputs}
        self._outputs = {port.name: port for port in outputs}

    @property
    def nodes(self) -> tuple[NodeInstance, ...]:
        return tuple(self._nodes.values())

    @property
    def edges(self) -> tuple[WorkflowEdge, ...]:
        return tuple(self._edges)

    @property
    def inputs(self) -> tuple[WorkflowPort, ...]:
        return tuple(self._inputs.values())

    @property
    def outputs(self) -> tuple[WorkflowPort, ...]:
        return tuple(self._outputs.values())

    def export_input(
        self,
        name: str,
        node_id: str,
        node_port: str,
        registry: NodeRegistry,
        *,
        label: str | None = None,
    ) -> WorkflowPort:
        """Expose a free node input, including a parameter port, as a workflow input."""
        port = self._workflow_port(name, node_id, node_port, PortDirection.INPUT, registry, label)
        if any(
            edge.target_node == node_id and edge.target_port == node_port for edge in self.edges
        ):
            raise WorkflowValidationError(
                (
                    ValidationIssue(
                        ValidationCode.EXPORTED_INPUT_CONNECTED,
                        f"Exported input {node_id!r}.{node_port!r} must not be connected",
                        node_id=node_id,
                    ),
                )
            )
        if name in self._inputs:
            raise ValueError(f"Workflow input {name!r} already exists")
        self._inputs[name] = port
        return port

    add_input = export_input

    def export_output(
        self,
        name: str,
        node_id: str,
        node_port: str,
        registry: NodeRegistry,
        *,
        label: str | None = None,
    ) -> WorkflowPort:
        """Expose a node output as a workflow output."""
        port = self._workflow_port(name, node_id, node_port, PortDirection.OUTPUT, registry, label)
        if name in self._outputs:
            raise ValueError(f"Workflow output {name!r} already exists")
        self._outputs[name] = port
        return port

    add_output = export_output

    def input(self, name: str) -> WorkflowPort | None:
        return self._inputs.get(name)

    def output(self, name: str) -> WorkflowPort | None:
        return self._outputs.get(name)

    def executor(self, registry: NodeRegistry) -> WorkflowExecutorFunction:
        """Return a node-compatible callable for this workflow."""
        return lambda inputs, _parameters=None: self.execute(inputs, registry)

    def execute(self, inputs: Mapping[str, Any], registry: NodeRegistry) -> Mapping[str, Any]:
        """Execute this workflow with exported inputs and return exported outputs."""
        values = dict(inputs)
        unknown = set(values).difference(self._inputs)
        if unknown:
            raise WorkflowValidationError(
                (
                    ValidationIssue(
                        ValidationCode.INVALID_EXPORTED_PORT,
                        f"Unknown workflow inputs: {sorted(unknown)!r}",
                    ),
                )
            )
        injected: dict[str, dict[str, Any]] = {}
        for name, workflow_port in self._inputs.items():
            if name not in values:
                raise WorkflowValidationError(
                    (
                        ValidationIssue(
                            ValidationCode.MISSING_REQUIRED_INPUT,
                            f"Workflow input {name!r} is not provided",
                        ),
                    )
                )
            value = values[name]
            if not workflow_port.data_type.accepts(value):
                raise WorkflowValidationError(
                    (
                        ValidationIssue(
                            ValidationCode.TYPE_MISMATCH,
                            f"Workflow input {name!r} expected {workflow_port.data_type.label}, got {type(value).__name__}",
                        ),
                    )
                )
            injected.setdefault(workflow_port.node_id, {})[workflow_port.node_port] = value
        result = WorkflowExecutor(registry).run(self, initial_inputs=injected)
        return {
            name: result.node_outputs[port.node_id][port.node_port]
            for name, port in self._outputs.items()
        }

    def _workflow_port(
        self,
        name: str,
        node_id: str,
        node_port: str,
        direction: PortDirection,
        registry: NodeRegistry,
        label: str | None,
    ) -> WorkflowPort:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Workflow port names must be non-empty strings")
        definition = registry.get(self.require_node(node_id).definition_id)
        port = (
            None
            if definition is None
            else (
                definition.input_for_instance(node_port, self.require_node(node_id))
                if direction is PortDirection.INPUT
                else definition.output_for_instance(node_port, self.require_node(node_id))
            )
        )
        if port is None:
            raise WorkflowValidationError(
                (
                    ValidationIssue(
                        ValidationCode.INVALID_EXPORTED_PORT,
                        f"Node {node_id!r} has no {direction.value} port {node_port!r}",
                        node_id=node_id,
                    ),
                )
            )
        return WorkflowPort(
            name.strip(), node_id, node_port, direction, port.data_type, label, port.is_param
        )

    def get_node(self, node_id: str) -> NodeInstance | None:
        return self._nodes.get(node_id)

    def require_node(self, node_id: str) -> NodeInstance:
        node = self.get_node(node_id)
        if node is None:
            raise KeyError(f"Unknown workflow node {node_id!r}")
        return node

    def add_node(self, node: NodeInstance) -> None:
        if node.id in self._nodes:
            raise ValueError(f"Workflow node {node.id!r} already exists")
        self._nodes[node.id] = node

    def remove_node(self, node_id: str) -> None:
        self.require_node(node_id)
        del self._nodes[node_id]
        self._edges = [
            edge
            for edge in self._edges
            if edge.source_node != node_id and edge.target_node != node_id
        ]
        self._inputs = {
            name: port for name, port in self._inputs.items() if port.node_id != node_id
        }
        self._outputs = {
            name: port for name, port in self._outputs.items() if port.node_id != node_id
        }

    def sync_boundary_nodes(self, registry: NodeRegistry) -> None:
        """Synchronize public ports declared by workflow boundary nodes.

        Parameters
        ----------
        registry:
            Registry used to resolve boundary node port types.

        Raises
        ------
        ValueError
            If a boundary node has a blank or duplicate public name.
        """
        boundary_ids = {"workflow-input", "workflow-output"}
        inputs = {
            name: port
            for name, port in self._inputs.items()
            if self.require_node(port.node_id).definition_id not in boundary_ids
        }
        outputs = {
            name: port
            for name, port in self._outputs.items()
            if self.require_node(port.node_id).definition_id not in boundary_ids
        }

        for node in self.nodes:
            if node.definition_id not in boundary_ids:
                continue
            name = node.parameters.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Workflow boundary names must be non-empty strings")
            name = name.strip()
            if node.definition_id == "workflow-input":
                if name in inputs:
                    raise ValueError(f"Workflow input {name!r} already exists")
                inputs[name] = self._boundary_workflow_port(
                    name, node, PortDirection.INPUT, registry
                )
            else:
                if name in outputs:
                    raise ValueError(f"Workflow output {name!r} already exists")
                port = self._boundary_workflow_port(name, node, PortDirection.OUTPUT, registry)
                outputs[name] = port

        self._inputs = inputs
        self._outputs = outputs

    def boundary_port_type(self, node: NodeInstance, registry: NodeRegistry) -> DataType[Any]:
        """Infer the public type exposed by one workflow boundary node.

        Workflow inputs use a type that can safely reach every connected internal
        target through a direct connection or registered conversion. Workflow
        outputs use the type supplied by their connected internal source. An
        unconnected or ambiguous boundary retains its declared ``Any`` type.
        """
        definition = registry.require(node.definition_id)
        fallback = definition.input_for_instance("value", node)
        if fallback is None:
            raise ValueError(f"Workflow boundary node {node.id!r} has no value input")
        if node.definition_id == "workflow-output":
            source_edge = next(
                (
                    edge
                    for edge in self.edges
                    if edge.target_node == node.id and edge.target_port == "value"
                ),
                None,
            )
            if source_edge is None:
                return fallback.data_type
            source = self.get_node(source_edge.source_node)
            if source is None:
                return fallback.data_type
            source_definition = registry.get(source.definition_id)
            source_port = (
                None
                if source_definition is None
                else source_definition.output_for_instance(source_edge.source_port, source)
            )
            return fallback.data_type if source_port is None else source_port.data_type
        if node.definition_id != "workflow-input":
            raise ValueError(f"Node {node.id!r} is not a workflow boundary node")

        target_types: list[DataType[Any]] = []
        for edge in self.edges:
            if edge.source_node != node.id or edge.source_port != "value":
                continue
            target = self.get_node(edge.target_node)
            if target is None:
                continue
            target_definition = registry.get(target.definition_id)
            target_port = (
                None
                if target_definition is None
                else target_definition.input_for_instance(edge.target_port, target)
            )
            if target_port is not None:
                target_types.append(target_port.data_type)
        return self._common_source_type(target_types, fallback.data_type)

    def _boundary_workflow_port(
        self,
        name: str,
        node: NodeInstance,
        direction: PortDirection,
        registry: NodeRegistry,
    ) -> WorkflowPort:
        """Build one inferred public interface port from a boundary node."""
        return WorkflowPort(
            name,
            node.id,
            "value",
            direction,
            self.boundary_port_type(node, registry),
        )

    @staticmethod
    def _common_source_type(
        target_types: list[DataType[Any]], fallback: DataType[Any]
    ) -> DataType[Any]:
        """Return one specific type that can safely supply every target type."""
        if not target_types:
            return fallback
        from flowgraph.application.port_conversions import resolve_port_conversion

        candidates: list[DataType[Any]] = []
        for target_type in target_types:
            if target_type.python_type is object or any(
                target_type.id == candidate.id for candidate in candidates
            ):
                continue
            candidates.append(target_type)
        for candidate in candidates:
            if all(
                candidate.is_compatible_with(target_type)
                or resolve_port_conversion(candidate, target_type) is not None
                for target_type in target_types
            ):
                return candidate
        return fallback

    def rename_node(self, node_id: str, new_id: str) -> None:
        """Rename a node and update all incident edges atomically."""
        self.require_node(node_id)
        if not isinstance(new_id, str) or not new_id.strip():
            raise ValueError("Workflow node IDs must be non-empty strings")
        new_id = new_id.strip()
        if new_id != node_id and new_id in self._nodes:
            raise ValueError(f"Workflow node {new_id!r} already exists")
        if new_id == node_id:
            return

        node = self._nodes.pop(node_id)
        node.id = new_id
        self._nodes[new_id] = node
        self._edges = [
            replace(
                edge,
                source_node=new_id if edge.source_node == node_id else edge.source_node,
                target_node=new_id if edge.target_node == node_id else edge.target_node,
            )
            for edge in self._edges
        ]
        self._inputs = {
            name: replace(port, node_id=new_id if port.node_id == node_id else port.node_id)
            for name, port in self._inputs.items()
        }
        self._outputs = {
            name: replace(port, node_id=new_id if port.node_id == node_id else port.node_id)
            for name, port in self._outputs.items()
        }

    def add_edge(self, edge: WorkflowEdge, registry: NodeRegistry) -> None:
        """Add an edge transactionally if the resulting structure is valid."""
        candidate = [*self._edges, edge]
        issues = self._validate_edges(candidate, registry)
        if (edge.target_node, edge.target_port) in {
            (port.node_id, port.node_port) for port in self.inputs
        }:
            issues += (
                ValidationIssue(
                    ValidationCode.EXPORTED_INPUT_CONNECTED,
                    f"Exported input {edge.target_node!r}.{edge.target_port!r} must not be connected",
                    node_id=edge.target_node,
                    edge_id=edge.id,
                ),
            )
        if issues:
            raise WorkflowValidationError(issues)
        if self._has_cycle(candidate):
            raise WorkflowValidationError(
                (
                    ValidationIssue(
                        ValidationCode.CYCLE,
                        f"Connection {edge.id} would create a directed cycle",
                        edge_id=edge.id,
                    ),
                )
            )
        self._edges.append(edge)

    def remove_edge(self, edge: WorkflowEdge) -> None:
        self._edges.remove(edge)

    def edge_conversion(self, edge: WorkflowEdge, registry: NodeRegistry) -> PortConversion | None:
        """Return the registered conversion used by a valid edge, if it needs one."""
        from flowgraph.application.port_conversions import resolve_port_conversion

        source = self.get_node(edge.source_node)
        target = self.get_node(edge.target_node)
        if source is None or target is None:
            return None
        source_definition = registry.get(source.definition_id)
        target_definition = registry.get(target.definition_id)
        if source_definition is None or target_definition is None:
            return None
        source_port = source_definition.output_for_instance(edge.source_port, source)
        target_port = target_definition.input_for_instance(edge.target_port, target)
        if source_port is None or target_port is None:
            return None
        if target_port.accepts_type(source_port.data_type):
            return None
        return resolve_port_conversion(source_port.data_type, target_port.data_type)

    def validate(
        self, registry: NodeRegistry, *, require_complete: bool = True
    ) -> tuple[ValidationIssue, ...]:
        issues: list[ValidationIssue] = []
        for node in self.nodes:
            if registry.get(node.definition_id) is None:
                issues.append(
                    ValidationIssue(
                        ValidationCode.UNKNOWN_DEFINITION,
                        f"Node {node.id!r} uses unknown definition {node.definition_id!r}",
                        node_id=node.id,
                    )
                )
        issues.extend(self._validate_edges(self._edges, registry))
        exported_inputs = {(port.node_id, port.node_port) for port in self.inputs}
        issues.extend(
            ValidationIssue(
                ValidationCode.EXPORTED_INPUT_CONNECTED,
                f"Exported input {edge.target_node!r}.{edge.target_port!r} must not be connected",
                node_id=edge.target_node,
                edge_id=edge.id,
            )
            for edge in self.edges
            if (edge.target_node, edge.target_port) in exported_inputs
        )
        if self._has_cycle(self._edges):
            issues.append(
                ValidationIssue(ValidationCode.CYCLE, "Workflow contains a directed cycle")
            )
        if require_complete:
            connected = {(edge.target_node, edge.target_port) for edge in self._edges}
            for node in self.nodes:
                definition = registry.get(node.definition_id)
                if definition is None:
                    continue
                for port in definition._inputs(definition.ports_for_instance(node)):
                    if port.required and (node.id, port.name) not in connected:
                        issues.append(
                            ValidationIssue(
                                ValidationCode.MISSING_REQUIRED_INPUT,
                                f"Required input {node.id!r}.{port.name!r} is not connected",
                                node_id=node.id,
                            )
                        )
        return tuple(issues)

    def topological_order(self) -> tuple[str, ...]:
        """Return stable insertion-ordered topological node IDs."""
        successors: dict[str, list[str]] = {}
        indegree = {node.id: 0 for node in self.nodes}
        for edge in self._edges:
            if edge.source_node in indegree and edge.target_node in indegree:
                successors.setdefault(edge.source_node, []).append(edge.target_node)
                indegree[edge.target_node] += 1
        ready = [node.id for node in self.nodes if indegree[node.id] == 0]
        order: list[str] = []
        while ready:
            node_id = ready.pop(0)
            order.append(node_id)
            for target in successors.get(node_id, []):
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)
        if len(order) != len(self._nodes):
            raise WorkflowValidationError(
                (ValidationIssue(ValidationCode.CYCLE, "Workflow contains a directed cycle"),)
            )
        return tuple(order)

    def _validate_edges(
        self, edges: list[WorkflowEdge], registry: NodeRegistry
    ) -> tuple[ValidationIssue, ...]:
        issues: list[ValidationIssue] = []
        seen_edges: set[WorkflowEdge] = set()
        connected_inputs: set[tuple[str, str]] = set()
        for edge in edges:
            if edge in seen_edges:
                issues.append(
                    ValidationIssue(
                        ValidationCode.DUPLICATE_EDGE,
                        f"Duplicate connection {edge.id}",
                        edge_id=edge.id,
                    )
                )
                continue
            seen_edges.add(edge)
            input_address = (edge.target_node, edge.target_port)
            if input_address in connected_inputs:
                issues.append(
                    ValidationIssue(
                        ValidationCode.INPUT_ALREADY_CONNECTED,
                        f"Input {edge.target_node!r}.{edge.target_port!r} already has a connection",
                        edge_id=edge.id,
                    )
                )
            connected_inputs.add(input_address)

            source = self.get_node(edge.source_node)
            target = self.get_node(edge.target_node)
            if source is None or target is None:
                missing = edge.source_node if source is None else edge.target_node
                issues.append(
                    ValidationIssue(
                        ValidationCode.UNKNOWN_NODE,
                        f"Connection {edge.id} references unknown node {missing!r}",
                        edge_id=edge.id,
                    )
                )
                continue
            source_definition = registry.get(source.definition_id)
            target_definition = registry.get(target.definition_id)
            if source_definition is None or target_definition is None:
                continue
            source_port = source_definition.output_for_instance(edge.source_port, source)
            target_port = target_definition.input_for_instance(edge.target_port, target)
            if source_port is None:
                issues.append(
                    ValidationIssue(
                        ValidationCode.UNKNOWN_SOURCE_PORT,
                        f"Node {source.id!r} has no output port {edge.source_port!r}",
                        edge_id=edge.id,
                    )
                )
            if target_port is None:
                issues.append(
                    ValidationIssue(
                        ValidationCode.UNKNOWN_TARGET_PORT,
                        f"Node {target.id!r} has no input port {edge.target_port!r}",
                        edge_id=edge.id,
                    )
                )
            if (
                source_port is not None
                and target_port is not None
                and not target_port.accepts_type(source_port.data_type)
                and self.edge_conversion(edge, registry) is None
            ):
                issues.append(
                    ValidationIssue(
                        ValidationCode.TYPE_MISMATCH,
                        f"Cannot connect {source_port.data_type.id!r} output to "
                        f"{target_port.data_type.id!r} input ({edge.id})",
                        edge_id=edge.id,
                    )
                )
        return tuple(issues)

    def _has_cycle(self, edges: list[WorkflowEdge]) -> bool:
        successors: dict[str, list[str]] = {}
        for edge in edges:
            if edge.source_node in self._nodes and edge.target_node in self._nodes:
                successors.setdefault(edge.source_node, []).append(edge.target_node)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> bool:
            if node_id in visiting:
                return True
            if node_id in visited:
                return False
            visiting.add(node_id)
            if any(visit(target) for target in successors.get(node_id, [])):
                return True
            visiting.remove(node_id)
            visited.add(node_id)
            return False

        return any(visit(node.id) for node in self.nodes if node.id not in visited)


@dataclass(frozen=True)
class WorkflowRunResult:
    execution_order: tuple[str, ...]
    node_outputs: Mapping[str, Mapping[str, Any]]
    node_inputs: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


class WorkflowExecutor:
    """Execute a validated DAG synchronously and retain every node output."""

    def __init__(self, registry: NodeRegistry) -> None:
        self._registry = registry

    def run(
        self,
        graph: WorkflowGraph,
        *,
        node_ids: set[str] | None = None,
        initial_outputs: Mapping[str, Mapping[str, Any]] | None = None,
        initial_inputs: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> WorkflowRunResult:
        """Execute all nodes, or only *node_ids* using previously resolved outputs."""
        # Missing required connections are execution-time node failures, not
        # graph-wide failures. A malformed node must not prevent independent
        # branches from running and producing useful partial results.
        issues = graph.validate(self._registry, require_complete=False)
        if issues:
            raise WorkflowValidationError(issues)
        full_order = graph.topological_order()
        selected_ids = set(full_order) if node_ids is None else set(node_ids)
        unknown_ids = selected_ids.difference(full_order)
        if unknown_ids:
            raise KeyError(f"Unknown workflow nodes {sorted(unknown_ids)!r}")
        order = tuple(node_id for node_id in full_order if node_id in selected_ids)
        outputs: dict[str, Mapping[str, Any]] = dict(initial_outputs or {})
        resolved_inputs: dict[str, Mapping[str, Any]] = {}
        first_error: NodeExecutionError | None = None
        incoming = {node.id: [] for node in graph.nodes}
        for edge in graph.edges:
            incoming[edge.target_node].append(edge)

        for node_id in order:
            node = graph.require_node(node_id)
            definition = self._registry.require(node.definition_id)
            injected_inputs = dict((initial_inputs or {}).get(node_id, {}))
            connected_ports = {edge.target_port for edge in incoming[node_id]} | set(
                injected_inputs
            )
            missing_required = [
                port.name
                for port in definition._inputs(definition.ports_for_instance(node))
                if port.required and port.name not in connected_ports
            ]
            if missing_required:
                if first_error is None:
                    first_error = NodeExecutionError(
                        node.id,
                        node.definition_id,
                        "required inputs are not connected: " + ", ".join(missing_required),
                    )
                continue
            missing_sources = [
                edge for edge in incoming[node_id] if edge.source_node not in outputs
            ]
            if missing_sources:
                missing = ", ".join(edge.source_node for edge in missing_sources)
                if first_error is None:
                    first_error = NodeExecutionError(
                        node.id,
                        node.definition_id,
                        f"upstream outputs are unavailable from: {missing}",
                    )
                continue
            node_inputs: dict[str, Any] = dict(injected_inputs)
            input_error = False
            for edge in incoming[node_id]:
                value = outputs[edge.source_node][edge.source_port]
                conversion = graph.edge_conversion(edge, self._registry)
                if conversion is not None:
                    try:
                        value = conversion.convert(value)
                    except Exception as error:  # noqa: BLE001
                        if first_error is None:
                            first_error = NodeExecutionError(
                                node.id,
                                node.definition_id,
                                f"conversion {conversion.label} failed for {edge.id}: {error}",
                            )
                        input_error = True
                        continue
                target_port = definition.input_for_instance(edge.target_port, node)
                if target_port is None or not target_port.accepts(value):
                    if first_error is None:
                        expected = "unknown" if target_port is None else target_port.data_type.label
                        first_error = NodeExecutionError(
                            node.id,
                            node.definition_id,
                            f"input {edge.target_port!r} expected {expected}, "
                            f"got {type(value).__name__}",
                        )
                    input_error = True
                    continue
                node_inputs[edge.target_port] = value
            if input_error:
                continue
            resolved_inputs[node_id] = MappingProxyType(node_inputs)
            parameter_inputs = {
                port.name: node_inputs[port.name]
                for port in definition._inputs(definition.ports_for_instance(node))
                if port.is_param and port.name in node_inputs
            }
            # A connected parameter port is the authoritative source for that
            # parameter. Persist its resolved value so the UI and saved
            # workflow reflect the value used for this execution.
            node.parameters.update(parameter_inputs)
            try:
                raw_outputs = definition.execute_instance(
                    node, MappingProxyType(node_inputs), self._registry
                )
                node_outputs = {} if raw_outputs is None else dict(raw_outputs)
            except WorkflowError as error:
                if isinstance(error, NodeExecutionError):
                    if first_error is None:
                        first_error = error
                    continue
                raise
            except Exception as error:  # noqa: BLE001
                if first_error is None:
                    first_error = NodeExecutionError(node.id, node.definition_id, str(error))
                continue
            try:
                self._validate_outputs(node, definition, node_outputs)
            except NodeExecutionError as error:
                if first_error is None:
                    first_error = error
                continue
            outputs[node_id] = MappingProxyType(node_outputs)

        if first_error is not None:
            first_error.partial_result = self._partial_result(order, outputs, resolved_inputs)
            raise first_error

        return WorkflowRunResult(
            order,
            MappingProxyType({node_id: outputs[node_id] for node_id in order}),
            MappingProxyType(resolved_inputs),
        )

    @staticmethod
    def _partial_result(
        order: tuple[str, ...],
        outputs: Mapping[str, Mapping[str, Any]],
        resolved_inputs: Mapping[str, Mapping[str, Any]],
    ) -> WorkflowRunResult:
        """Build a result containing every successfully completed node."""
        completed = tuple(node_id for node_id in order if node_id in outputs)
        return WorkflowRunResult(
            completed,
            MappingProxyType({node_id: outputs[node_id] for node_id in completed}),
            MappingProxyType({node_id: resolved_inputs[node_id] for node_id in completed}),
        )

    @staticmethod
    def _validate_outputs(
        node: NodeInstance, definition: NodeDefinition, outputs: dict[str, Any]
    ) -> None:
        expected = {
            port.name: port for port in definition._outputs(definition.ports_for_instance(node))
        }
        if set(outputs) != set(expected):
            raise NodeExecutionError(
                node.id,
                node.definition_id,
                f"expected outputs {sorted(expected)}, received {sorted(outputs)}",
            )
        for name, value in outputs.items():
            data_type = expected[name].data_type
            if not data_type.accepts(value):
                raise NodeExecutionError(
                    node.id,
                    node.definition_id,
                    f"output {name!r} expected {data_type.label}, got {type(value).__name__}",
                )
