"""Execute trusted SciJava Groovy scripts through optional PyImageJ."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from flowgraph.application.workflow_core import (
    ExecContext,
    NodeDefinition,
    NodeInstance,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
)
from flowgraph.domain.filepath import FilePath

from .data_types import ANY, BOOLEAN, FILE, FLOAT, IMAGEJ, INTEGER, STRING, ParameterKind

# Fiji's Scala and JavaScript scripting plugins need these runtimes on Java 21.
# Pin the tested Fiji release so its transitive plugins remain compatible.
FIJI_ENDPOINTS = (
    "sc.fiji:fiji:2.18.0",
    "org.scala-lang:scala-library:2.13.10",
    "org.openjdk.nashorn:nashorn-core:15.7",
)
DEFAULT_CODE = """#@ Dataset image
#@output Dataset result

result = image
"""
_DECLARATION = re.compile(
    r"^\s*#@\s*(?:(input|output)\s+)?([\w.]+)\s+"
    r"(?:\([^\n]*\)\s*)?([A-Za-z_$][\w$]*)\s*$",
    re.IGNORECASE,
)
_UNTYPED_OUTPUT = re.compile(r"^\s*#@output\s+([A-Za-z_$][\w$]*)\s*$", re.IGNORECASE)
_TYPES = {
    "String": STRING,
    "Boolean": BOOLEAN,
    "boolean": BOOLEAN,
    "Integer": INTEGER,
    "int": INTEGER,
    "Long": INTEGER,
    "long": INTEGER,
    "Double": FLOAT,
    "double": FLOAT,
    "Float": FLOAT,
    "float": FLOAT,
    "Dataset": IMAGEJ,
    "Img": IMAGEJ,
    "RandomAccessibleInterval": IMAGEJ,
}


def _file_source(parameters: Mapping[str, Any]) -> str:
    """Read a configured Groovy file."""
    filename = parameters.get("filename", "")
    if not filename or (isinstance(filename, FilePath) and filename.primary == Path(".")):
        raise ValueError("ImageJ Groovy script filename must not be empty")
    if not isinstance(filename, (str, Path, FilePath)):
        raise TypeError("ImageJ script filename must be a path")
    path = Path(filename).expanduser()
    if path.suffix.lower() != ".groovy":
        raise ValueError("ImageJ script filename must end in .groovy")
    return _validated_source(path.read_text(encoding="utf-8"))


def _validated_source(source: Any) -> str:
    """Reject absent or empty Groovy source."""
    if not isinstance(source, str) or not source.strip():
        raise ValueError("ImageJ Groovy script must not be empty")
    return source


def _declarations(source: str) -> tuple[tuple[PortDefinition, str], ...]:
    """Infer named ports from SciJava #@ declarations without executing the script."""
    declarations: list[tuple[PortDefinition, str]] = []
    names: set[str] = set()
    for line in source.splitlines():
        match = _DECLARATION.fullmatch(line)
        if match:
            qualifier, declared_type, name = match.groups()
            short_type = declared_type.rsplit(".", 1)[-1]
            if qualifier != "output" and short_type.endswith("Service"):
                continue  # SciJava injects service inputs itself.
            data_type = _TYPES.get(short_type, ANY)
            direction = PortDirection.OUTPUT if qualifier == "output" else PortDirection.INPUT
        else:
            untyped = _UNTYPED_OUTPUT.fullmatch(line)
            if untyped is None:
                continue
            name = untyped.group(1)
            short_type = "Object"
            data_type = ANY
            direction = PortDirection.OUTPUT
        if name in names:
            raise ValueError(f"Duplicate ImageJ script port {name!r}")
        names.add(name)
        declarations.append((PortDefinition(name, direction, data_type, name), short_type))
    return tuple(declarations)


def _code_ports_for_instance(instance: NodeInstance) -> tuple[PortDefinition, ...]:
    """Resolve editor script ports without loading the JVM."""
    return tuple(
        port
        for port, _ in _declarations(
            _validated_source(instance.parameters.get("code", DEFAULT_CODE))
        )
    )


def _file_ports_for_instance(instance: NodeInstance) -> tuple[PortDefinition, ...]:
    """Expose the filename parameter port and declarations from the selected file."""
    filename_port = PortDefinition(
        "filename", PortDirection.INPUT, FILE, "Groovy script file", required=False, is_param=True
    )
    filename = instance.parameters.get("filename", "")
    if not filename or (isinstance(filename, FilePath) and filename.primary == Path(".")):
        return (filename_port,)
    script_ports = tuple(port for port, _ in _declarations(_file_source(instance.parameters)))
    if any(port.name == "filename" for port in script_ports):
        raise ValueError("ImageJ script port 'filename' conflicts with the filename parameter")
    return (filename_port, *script_ports)


def _execute_script(
    inputs: Mapping[str, Any],
    source: str,
) -> Mapping[str, Any]:
    """Execute Groovy and return declared outputs using their script names."""
    declarations = _declarations(source)
    try:
        import imagej
    except ImportError as error:
        raise RuntimeError("ImageJ scripts require the optional pyimagej package") from error

    import scyjava

    # Fiji includes plugins compiled for Java 21. ScyJava otherwise
    # downloads Java 11 by default, even when a newer system Java is installed.
    if not scyjava.jvm_started():
        scyjava.config.set_java_constraints(fetch="auto", version="21")

    ij = imagej.init(list(FIJI_ENDPOINTS), mode="headless")
    args: dict[str, Any] = {}
    for port, declared_type in declarations:
        if port.direction is not PortDirection.INPUT or port.name not in inputs:
            continue
        value = inputs[port.name]
        if declared_type == "Dataset":
            value = ij.py.to_dataset(value)
        elif declared_type in {"Img", "RandomAccessibleInterval"}:
            value = ij.py.to_img(value)
        else:
            value = ij.py.to_java(value)
        args[port.name] = value

    result = ij.py.run_script("Groovy", source, args)
    outputs: dict[str, Any] = {}
    for port, _ in declarations:
        if port.direction is not PortDirection.OUTPUT:
            continue
        if port.name not in result:
            raise ValueError(f"ImageJ script did not produce output {port.name!r}")
        value = ij.py.from_java(result[port.name])
        outputs[port.name] = np.asarray(value).copy() if port.data_type == IMAGEJ else value
    return outputs


def _execute_code(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Execute the editor's Groovy script."""
    return _execute_script(inputs, _validated_source(parameters.get("code", DEFAULT_CODE)))


def _execute_file(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Execute the Groovy file, honoring a connected filename parameter."""
    filename = inputs.get("filename", parameters.get("filename", ""))
    return _execute_script(inputs, _file_source({"filename": filename}))


IMAGEJ_SCRIPT = NodeDefinition(
    id="imagej-script",
    requirements=("py:pyimagej", "py:numpy"),
    icon="mdi-image-filter-center-focus",
    label="ImageJ Groovy Script",
    description="Runs trusted Groovy code entered in the editor; #@ declarations define ports.",
    ports=(),
    executor=_execute_code,
    instance_port_resolver=_code_ports_for_instance,
    parameters=(ParameterDefinition("code", STRING, "Groovy script", DEFAULT_CODE, port=False),),
    presentation="code",
)

IMAGEJ_SCRIPT_FILE = NodeDefinition(
    id="imagej-script-file",
    requirements=("py:pyimagej", "py:numpy"),
    icon="mdi-file-code-outline",
    label="ImageJ Groovy Script File",
    description="Runs a Groovy file in Fiji; #@ declarations define ports.",
    ports=(),
    executor=_execute_file,
    instance_port_resolver=_file_ports_for_instance,
    parameters=(
        ParameterDefinition(
            "filename",
            ParameterKind.FILE,
            "Groovy script file",
            "",
            "script.groovy",
            file_patterns=("*.groovy",),
            port=True,
        ),
    ),
)

AVAILABLE_NODES = (IMAGEJ_SCRIPT, IMAGEJ_SCRIPT_FILE)

__all__ = ["AVAILABLE_NODES", "DEFAULT_CODE", "IMAGEJ_SCRIPT", "IMAGEJ_SCRIPT_FILE"]
