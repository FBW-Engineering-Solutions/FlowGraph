"""Explicit automatic conversions permitted between workflow port types."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np

from flowgraph.adapters.data_types import (
    BOOLEAN,
    FLOAT,
    IMAGE,
    IMAGEJ,
    INTEGER,
    MUSCAT_ELEMENT_FILTER,
    MUSCAT_NODE_FILTER,
    STRING,
    VEC2D,
    VEC2DI,
    VEC3D,
    VEC3DI,
)
from flowgraph.application.workflow_core import DataType
from flowgraph.domain.filepath import FilePath


@dataclass(frozen=True)
class PortConversion:
    """A directed value conversion between two stable workflow type IDs."""

    source_type_id: str
    target_type_id: str
    label: str
    convert: Callable[[Any], Any]


BOOLEAN_TO_STRING = PortConversion("boolean", "string", "Boolean → Text", str)
BOOLEAN_TO_INTEGER = PortConversion("boolean", "integer", "Boolean → Integer", int)
BOOLEAN_TO_FLOAT = PortConversion("boolean", "float", "Boolean → Float", float)

ELEMENT_FILTER_TO_NODE_FILTER = PortConversion(
    MUSCAT_ELEMENT_FILTER.id,
    MUSCAT_NODE_FILTER.id,
    "Element Selector → Node Selector",
    lambda value: value,
)

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

# FILE_TO_PPATH = PortConversion("FilePath", "string", "FilePath → Text", str)
# PPATH_TO_FILE = PortConversion("string", "FilePath", "Text → FilePath", File)


FILE_TO_STR = PortConversion("filename", "string", "FilePath → Text", str)
STR_TO_FILE = PortConversion("string", "filename", "Text → FilePath", FilePath)


PATH_TO_STR = PortConversion("dirname", "string", "dirname → Text", str)
STR_TO_PATH = PortConversion("string", "dirname", "Text → dirname", Path)

VEC3D_TO_LIST = PortConversion(
    "VEC3D", "list[float]", "Tex3D Vector → list[float]", lambda x: list(x)
)

PILLOW_TO_IMAGEJ = PortConversion(
    IMAGE.id,
    IMAGEJ.id,
    "Pillow Image → ImageJ NumPy",
    lambda image: np.array(image, copy=True),
)


def _convert_vector(value: list[Any], *, dimensions: int, integer: bool) -> list[Any]:
    """Resize a vector and cast components without modifying the source list."""
    cast = round if integer else float
    components = value[:dimensions] + [0] * max(0, dimensions - len(value))
    return [cast(component) for component in components]


_VECTOR_TYPES = ((VEC2D, 2, False), (VEC3D, 3, False), (VEC2DI, 2, True), (VEC3DI, 3, True))
VECTOR_CONVERSIONS = tuple(
    PortConversion(
        source.id,
        target.id,
        f"{source.label} → {target.label}",
        partial(_convert_vector, dimensions=dimensions, integer=integer),
    )
    for source, _, _ in _VECTOR_TYPES
    for target, dimensions, integer in _VECTOR_TYPES
    if source.id != target.id
)


PORT_CONVERSIONS = (
    ELEMENT_FILTER_TO_NODE_FILTER,
    BOOLEAN_TO_STRING,
    BOOLEAN_TO_INTEGER,
    BOOLEAN_TO_FLOAT,
    INTEGER_TO_FLOAT,
    INTEGER_TO_STRING,
    INTEGER_TO_LIST_INT,
    FLOAT_TO_INTEGER,
    FLOAT_TO_STRING,
    FLOAT_TO_LIST_FLOAT,
    PATH_TO_STR,
    STR_TO_PATH,
    VEC3D_TO_LIST,
    PILLOW_TO_IMAGEJ,
    FILE_TO_STR,
    STR_TO_FILE,
    *VECTOR_CONVERSIONS,
)


_CONVERSIONS_BY_TYPE_IDS = {
    (conversion.source_type_id, conversion.target_type_id): conversion
    for conversion in PORT_CONVERSIONS
}


def resolve_port_conversion(source: DataType[Any], target: DataType[Any]) -> PortConversion | None:
    """Return the explicitly registered conversion from *source* to *target*, if any."""
    return _CONVERSIONS_BY_TYPE_IDS.get((source.id, target.id))


_SOURCE_DATA_TYPES = {
    BOOLEAN.id: BOOLEAN,
    STRING.id: STRING,
    INTEGER.id: INTEGER,
    FLOAT.id: FLOAT,
    VEC3D.id: VEC3D,
    VEC2D.id: VEC2D,
    VEC2DI.id: VEC2DI,
    VEC3DI.id: VEC3DI,
    IMAGE.id: IMAGE,
}


def resolve_value_conversion(value: Any, target: DataType[Any]) -> PortConversion | None:
    """Return a registered conversion for a runtime value and target type."""
    # bool subclasses int, but an integer target must receive an actual int.
    if isinstance(value, bool) and target.id == INTEGER.id:
        return resolve_port_conversion(BOOLEAN, target)
    if target.accepts(value):
        return None
    for conversion in PORT_CONVERSIONS:
        if conversion.target_type_id != target.id:
            continue
        source = _SOURCE_DATA_TYPES.get(conversion.source_type_id)
        if source is not None and source.accepts(value):
            return conversion
    return None
