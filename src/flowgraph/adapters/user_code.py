"""Workflow node for executing user-provided Python code."""

from __future__ import annotations

import ast
import inspect
from collections.abc import Mapping
from typing import Any

from flowgraph.application.workflow_core import (
    NodeDefinition,
    NodeInstance,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
)

from .data_types import ANY, BOOLEAN, FLOAT, INTEGER, LIST_FLOAT, LIST_INT, LIST_STR, STRING

DEFAULT_CODE = """def Execute(input1, input2, input3) -> tuple[Any, Any, Any]:
    return (input1, input2, input3)
"""

_ANNOTATION_TYPES = {
    "Any": ANY,
    "bool": BOOLEAN,
    "float": FLOAT,
    "int": INTEGER,
    "list[float]": LIST_FLOAT,
    "list[int]": LIST_INT,
    "list[str]": LIST_STR,
    "str": STRING,
}


def _annotation_name(annotation: ast.expr | None) -> str:
    """Return the supported source spelling for one function annotation."""
    if annotation is None:
        return "Any"
    if isinstance(annotation, ast.Name):
        return annotation.id
    if (
        isinstance(annotation, ast.Subscript)
        and isinstance(annotation.value, ast.Name)
        and annotation.value.id == "list"
        and isinstance(annotation.slice, ast.Name)
    ):
        return f"list[{annotation.slice.id}]"
    return ast.unparse(annotation)


def _execute_function(source: str) -> ast.FunctionDef:
    """Parse *source* and return its top-level ``Execute`` function declaration."""
    if not isinstance(source, str) or not source.strip():
        raise ValueError("The user function code must be non-empty Python source")
    try:
        module = ast.parse(source, filename="<flowgraph user-function>", mode="exec")
    except SyntaxError as error:
        raise ValueError(f"The user function code is invalid Python: {error.msg}") from error
    functions = [
        statement
        for statement in module.body
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))
        and statement.name == "Execute"
    ]
    if len(functions) != 1:
        raise ValueError(
            "The user function code must define exactly one top-level Execute function"
        )
    function = functions[0]
    if isinstance(function, ast.AsyncFunctionDef):
        raise TypeError("Execute must be a regular function, not an async function")
    return function


def _input_ports(source: str) -> tuple[PortDefinition, ...]:
    """Extract validated typed input ports from a user ``Execute`` declaration."""
    function = _execute_function(source)
    arguments = function.args
    if arguments.vararg is not None or arguments.kwarg is not None or arguments.kwonlyargs:
        raise ValueError(
            "Execute may use only positional parameters; *args and keyword-only parameters are unsupported"
        )
    inputs = [*arguments.posonlyargs, *arguments.args]
    ports: list[PortDefinition] = []
    for argument in inputs:
        annotation_name = _annotation_name(argument.annotation)
        data_type = _ANNOTATION_TYPES.get(annotation_name)
        if data_type is None:
            supported = ", ".join(_ANNOTATION_TYPES)
            raise ValueError(
                f"Unsupported annotation for Execute parameter {argument.arg!r}: "
                f"{annotation_name!r}. Supported annotations are {supported}."
            )
        ports.append(
            PortDefinition(
                argument.arg, PortDirection.INPUT, data_type, argument.arg, required=False
            )
        )
    return tuple(ports)


def _output_ports(source: str) -> tuple[PortDefinition, ...]:
    """Extract validated typed output ports from a user ``Execute`` return annotation."""
    annotation = _execute_function(source).returns
    if not (
        isinstance(annotation, ast.Subscript)
        and isinstance(annotation.value, ast.Name)
        and annotation.value.id == "tuple"
    ):
        raise ValueError("Execute must declare a fixed-length tuple return annotation")
    elements = (
        list(annotation.slice.elts)
        if isinstance(annotation.slice, ast.Tuple)
        else [annotation.slice]
    )
    ports: list[PortDefinition] = []
    for index, element in enumerate(elements, start=1):
        annotation_name = _annotation_name(element)
        data_type = _ANNOTATION_TYPES.get(annotation_name)
        if data_type is None:
            supported = ", ".join(_ANNOTATION_TYPES)
            raise ValueError(
                f"Unsupported annotation for Execute output {index}: {annotation_name!r}. "
                f"Supported annotations are {supported}."
            )
        ports.append(
            PortDefinition(f"output{index}", PortDirection.OUTPUT, data_type, f"Output {index}")
        )
    return tuple(ports)


def _ports_for_instance(instance: NodeInstance) -> tuple[PortDefinition, ...]:
    """Resolve User Function inputs and outputs from an instance's source code."""
    source = instance.parameters.get("code", DEFAULT_CODE)
    return _input_ports(source) + _output_ports(source)


def _execute_user_code(
    inputs: Mapping[str, Any], parameters: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Compile and run the user's ``Execute`` function in a trusted local namespace."""
    code = parameters.get("code", DEFAULT_CODE)
    input_ports = _input_ports(code)
    output_ports = _output_ports(code)

    namespace: dict[str, Any] = {"__builtins__": __builtins__, "Any": Any}
    compiled = compile(code, "<flowgraph user-function>", "exec")
    exec(compiled, namespace)  # noqa: S102 - this node intentionally runs trusted user code
    function = namespace.get("Execute")
    if not callable(function):
        raise TypeError("The user function code must define callable Execute")

    signature = inspect.signature(function)
    function_parameters = list(signature.parameters.values())
    if [parameter.name for parameter in function_parameters] != [
        port.name for port in input_ports
    ] or any(
        parameter.kind
        not in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        for parameter in function_parameters
    ):
        raise ValueError("Execute must not be reassigned after its validated function declaration")

    result = function(*(inputs.get(port.name) for port in input_ports))
    if not isinstance(result, tuple) or len(result) != len(output_ports):
        raise TypeError(
            f"Execute must return a tuple containing exactly {len(output_ports)} outputs"
        )
    return {port.name: value for port, value in zip(output_ports, result, strict=True)}


USER_FUNCTION = NodeDefinition(
    id="user-function",
    icon="mdi-code-braces",
    label="User Function",
    description="Runs trusted local Python code defining a typed Execute function.",
    ports=(),
    executor=_execute_user_code,
    instance_port_resolver=_ports_for_instance,
    parameters=(
        ParameterDefinition(
            "code",
            STRING,
            "Execute code",
            DEFAULT_CODE,
            "def Execute(value: float): ...",
            port=False,
        ),
    ),
    presentation="code",
)

AVAILABLE_NODES = (USER_FUNCTION,)

__all__ = ["AVAILABLE_NODES", "DEFAULT_CODE", "USER_FUNCTION"]
