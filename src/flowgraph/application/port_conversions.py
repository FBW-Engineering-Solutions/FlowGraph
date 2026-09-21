"""Explicit automatic conversions permitted between workflow port types."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from flowgraph.application.workflow_core import DataType


@dataclass(frozen=True)
class PortConversion:
    """A directed value conversion between two stable workflow type IDs."""

    source_type_id: str
    target_type_id: str
    label: str
    convert: Callable[[Any], Any]


INTEGER_TO_FLOAT = PortConversion("integer", "float", "Integer → Float", float)
INTEGER_TO_STRING = PortConversion("integer", "string", "Integer → string", str)
INTEGER_TO_LIST_INT = PortConversion(
    "integer", "list[int]", "Integer → list[int]", lambda value: [value]
)

FLOAT_TO_INTEGER = PortConversion("float", "integer", "Float -> Integer", round)
FLOAT_TO_STRING = PortConversion("float", "string", "Float → Text", str)
FLOAT_TO_LIST_FLOAT = PortConversion(
    "float", "list[float]", "Float → list[float]", lambda value: [value]
)

PATH_TO_STR = PortConversion("filename", "string", "filename → Text", str)
STR_TO_PATH = PortConversion("string", "filename", "Text → filename", str)

VEC3D_TO_LIST = PortConversion(
    "VEC3D", "list[float]", "Tex3D Vector → list[float]", lambda x: list(x)
)


PORT_CONVERSIONS = (
    INTEGER_TO_FLOAT,
    INTEGER_TO_STRING,
    INTEGER_TO_LIST_INT,
    FLOAT_TO_INTEGER,
    FLOAT_TO_STRING,
    FLOAT_TO_LIST_FLOAT,
    PATH_TO_STR,
    STR_TO_PATH,
    VEC3D_TO_LIST,
)


_CONVERSIONS_BY_TYPE_IDS = {
    (conversion.source_type_id, conversion.target_type_id): conversion
    for conversion in PORT_CONVERSIONS
}


def resolve_port_conversion(source: DataType[Any], target: DataType[Any]) -> PortConversion | None:
    """Return the explicitly registered conversion from *source* to *target*, if any."""
    return _CONVERSIONS_BY_TYPE_IDS.get((source.id, target.id))
