"""CoSApp workflow adapter for executing external trusted Python models."""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from flowgraph.application.workflow_core import (
    NodeDefinition,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
)

from .data_types import ANY, FILE, STRING

COSAPP_RESULT_PORT = PortDefinition("result", PortDirection.OUTPUT, ANY, "CoSApp system")


def _path_mapping(value: object, parameter_name: str) -> dict[str, str]:
    """Parse one JSON mapping of FlowGraph port names to CoSApp attribute paths."""
    if not isinstance(value, str):
        raise TypeError(f"The {parameter_name} parameter must be a JSON object")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"The {parameter_name} parameter must be valid JSON: {error.msg}"
        ) from error
    if not isinstance(parsed, dict):
        raise TypeError(f"The {parameter_name} parameter must be a JSON object")

    paths: dict[str, str] = {}
    for port_name, attribute_path in parsed.items():
        if not isinstance(port_name, str) or not port_name.strip():
            raise ValueError(f"The {parameter_name} mapping contains an empty port name")
        if not isinstance(attribute_path, str) or not attribute_path.strip():
            raise ValueError(
                f"The {parameter_name} mapping for {port_name!r} must contain a non-empty path"
            )
        if any(not segment.isidentifier() for segment in attribute_path.split(".")):
            raise ValueError(
                f"The {parameter_name} path for {port_name!r} must be dot-separated identifiers"
            )
        paths[port_name] = attribute_path
    return paths


def _ports(parameters: Mapping[str, Any]) -> tuple[PortDefinition, ...]:
    """Return ports declared by the node's persisted CoSApp interface mappings."""
    input_paths = _path_mapping(parameters.get("inputs", "{}"), "inputs")
    output_paths = _path_mapping(parameters.get("outputs", "{}"), "outputs")
    _validate_output_paths(output_paths)
    return (
        *(PortDefinition(name, PortDirection.INPUT, ANY, name) for name in input_paths),
        COSAPP_RESULT_PORT,
        *(PortDefinition(name, PortDirection.OUTPUT, ANY, name) for name in output_paths),
    )


def _validate_output_paths(output_paths: Mapping[str, str]) -> None:
    """Reject output names that conflict with the permanent CoSApp result port."""
    if "result" in output_paths:
        raise ValueError("The outputs mapping cannot use reserved output name 'result'")


def _load_model(module_path: object, factory_name: object) -> Any:
    """Load and construct a root CoSApp ``System`` from a trusted Python file."""
    if not isinstance(module_path, str) or not module_path.strip():
        raise ValueError("The CoSApp model file must be a non-empty Python file path")
    if not isinstance(factory_name, str) or not factory_name.strip():
        raise ValueError("The CoSApp factory name must be a non-empty attribute name")

    path = Path(module_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"CoSApp model file does not exist: {path}")
    specification = importlib.util.spec_from_file_location(
        f"flowgraph_cosapp_model_{abs(hash(path.resolve()))}", path
    )
    if specification is None or specification.loader is None:
        raise ImportError(f"Could not load the CoSApp model file: {path}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)

    factory = getattr(module, factory_name, None)
    if not callable(factory):
        raise TypeError(f"CoSApp model file must define callable {factory_name!r}")
    model = factory()

    try:
        from cosapp.base import System
    except ImportError as error:
        raise ImportError(
            "CoSApp is required to execute this node. Install FlowGraph with its 'cosapp' extra."
        ) from error
    if not isinstance(model, System):
        raise TypeError(f"CoSApp factory {factory_name!r} must return a cosapp.base.System")
    return model


def _resolve_parent(model: object, path: str) -> tuple[object, str]:
    """Return the object and final attribute addressed by a declared CoSApp path."""
    parent = model
    *parents, name = path.split(".")
    for segment in parents:
        try:
            parent = getattr(parent, segment)
        except AttributeError as error:
            raise ValueError(f"CoSApp path {path!r} cannot resolve {segment!r}") from error
    return parent, name


def _set_path(model: object, path: str, value: Any) -> None:
    """Set a declared CoSApp input attribute path."""
    parent, name = _resolve_parent(model, path)
    if not hasattr(parent, name):
        raise ValueError(f"CoSApp input path {path!r} does not exist")
    setattr(parent, name, value)


def _get_path(model: object, path: str) -> Any:
    """Read a declared CoSApp output attribute path."""
    parent, name = _resolve_parent(model, path)
    try:
        return getattr(parent, name)
    except AttributeError as error:
        raise ValueError(f"CoSApp output path {path!r} does not exist") from error


def _execute_cosapp(inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Construct, configure, execute, and export one CoSApp model instance."""
    input_paths = _path_mapping(parameters.get("inputs", "{}"), "inputs")
    output_paths = _path_mapping(parameters.get("outputs", "{}"), "outputs")
    _validate_output_paths(output_paths)
    model = _load_model(parameters.get("model_file"), parameters.get("factory"))
    for port_name, path in input_paths.items():
        _set_path(model, path, inputs[port_name])
    model.run_drivers()
    return {
        "result": model,
        **{name: _get_path(model, path) for name, path in output_paths.items()},
    }


COSAPP_WORKFLOW = NodeDefinition(
    id="cosapp-workflow",
    icon="mdi-play-network-outline",
    label="CoSApp Workflow",
    description="Executes a trusted external CoSApp System and exports declared result paths.",
    ports=(COSAPP_RESULT_PORT,),
    executor=_execute_cosapp,
    parameters=(
        ParameterDefinition(
            "model_file",
            FILE,
            "CoSApp model file",
            "",
            "Path to a trusted Python file defining the CoSApp model",
            file_patterns=("*.py",),
            port=False,
        ),
        ParameterDefinition(
            "factory",
            STRING,
            "Model factory",
            "create_model",
            "Zero-argument callable returning the root CoSApp System",
            port=False,
        ),
        ParameterDefinition(
            "inputs",
            STRING,
            "Input paths",
            "{}",
            'JSON mapping of FlowGraph input names to CoSApp paths, e.g. {"current": "source.I"}',
            port=False,
        ),
        ParameterDefinition(
            "outputs",
            STRING,
            "Output paths",
            "{}",
            'JSON mapping of FlowGraph output names to CoSApp paths, e.g. {"voltage": "circuit.n1.V"}',
            port=False,
        ),
    ),
    port_resolver=_ports,
)

AVAILABLE_NODES = (COSAPP_WORKFLOW,)

__all__ = ["AVAILABLE_NODES", "COSAPP_WORKFLOW"]
