"""Trusted Python-expression calculator with positional and upstream-name inputs."""

import builtins
import keyword
import re
from collections import Counter
from collections.abc import Mapping
from typing import Any

import numpy as np

from flowgraph.application.workflow_core import (
    ExecContext,
    NodeDefinition,
    NodeInstance,
    NodeRegistry,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
    WorkflowEdge,
)

from .data_types import ANY, ParameterKind


def _numeric_value(value: Any, label: str) -> Any:
    """Normalize lists and expose numeric array storage through a read-only view."""
    if isinstance(value, list):
        value = np.asarray(value)
    if isinstance(value, np.ndarray):
        if value.dtype.kind not in "buifc":
            raise TypeError(f"Calculator {label} must contain numeric values")
        view = value.view(np.ndarray)
        view.flags.writeable = False
        return view
    if isinstance(value, (bool, int, float, complex, np.number, np.bool_)):
        if np.asarray(value).dtype.kind not in "buifc":
            raise TypeError(f"Calculator {label} must be numeric")
        return value.item() if isinstance(value, np.generic) else value
    raise TypeError(f"Calculator {label} must be a numeric scalar or NumPy array")


def _calculate(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    input_edges: Mapping[str, WorkflowEdge],
) -> Mapping[str, Any]:
    """Evaluate one trusted expression; this is intentionally not a sandbox."""
    formula = inputs.get("formula", parameters.get("formula", "0"))
    if not isinstance(formula, str) or not formula.strip():
        raise ValueError("Calculator formula must be a non-empty Python expression")

    namespace = {
        name: _numeric_value(inputs[name], f"input {name!r}")
        for index in range(1, 126)
        if (name := f"input_{index}") in inputs
    }
    data_names = frozenset(namespace)
    names = Counter(edge.source_port for name, edge in input_edges.items() if name in data_names)
    for name, edge in input_edges.items():
        alias = edge.source_port
        if (
            name in data_names
            and names[alias] == 1
            and alias.isidentifier()
            and not keyword.iskeyword(alias)
            and not re.fullmatch(r"input_[0-9]+", alias)
            and alias not in {"np", "__builtins__"}
            and not hasattr(builtins, alias)
        ):
            namespace[alias] = namespace[name]
    namespace.update(np=np, __builtins__=builtins.__dict__)
    try:
        # One shared namespace also makes aliases available inside comprehensions/lambdas.
        result = eval(compile(formula.strip(), "<calculator formula>", "eval"), namespace)
    except Exception as error:
        raise ValueError(f"Calculator formula failed ({type(error).__name__}): {error}") from error
    if isinstance(result, list):
        raise TypeError("Calculator result must be a numeric scalar or NumPy array; use np.array")
    return {"result": _numeric_value(result, "result")}


def _calculator(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Evaluate using numbered names when called without workflow provenance."""
    return _calculate(inputs, parameters, {})


def _calculator_instance(
    _instance: NodeInstance,
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _registry: NodeRegistry,
    input_edges: Mapping[str, WorkflowEdge],
    _exec_context: ExecContext,
) -> Mapping[str, Any]:
    """Resolve optional aliases from actual upstream output port names."""
    return _calculate(inputs, parameters, input_edges)


CALCULATOR = NodeDefinition(
    id="calculator",
    label="Calculator",
    icon="mdi-calculator",
    description="Evaluate a trusted Python expression with np, numbered inputs and unique aliases.",
    requirements=("py:numpy",),
    ports=(
        PortDefinition("input", PortDirection.INPUT, ANY, "Input", required=False, expandable=125),
        PortDefinition("result", PortDirection.OUTPUT, ANY, "Result"),
    ),
    parameters=(ParameterDefinition("formula", ParameterKind.TEXT, "Formula", "0", "input_1 * 2"),),
    executor=_calculator,
    edge_aware_instance_executor=_calculator_instance,
    cache_policy="always",
)

__all__ = ["CALCULATOR"]
