"""Value extraction and demand-driven statistics for one-dimensional numeric data."""

from collections.abc import Mapping
from typing import Any

import numpy as np

from flowgraph.application.workflow_core import (
    ExecContext,
    NodeDefinition,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
)

from .data_types import ARRAY_1D, FLOAT, INTEGER, ParameterKind


def _scalars_to_array_1d(
    inputs: Mapping[str, Any],
    _parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Collect connected scalar slots in numeric order into one read-only array."""

    def values():
        for index in range(1, 126):
            name = f"scalar_{index}"
            if name not in inputs:
                continue
            value = inputs[name]
            if isinstance(value, (bool, np.bool_)) or not isinstance(
                value, (int, float, np.integer, np.floating)
            ):
                raise TypeError(f"Scalars to 1D Array input {name!r} must be a real scalar")
            yield value

    count = sum(f"scalar_{index}" in inputs for index in range(1, 126))
    array = np.fromiter(values(), dtype=np.float64, count=count)
    array.flags.writeable = False
    return {"array": array}


SCALARS_TO_ARRAY_1D = NodeDefinition(
    id="scalars-to-array-1d",
    label="Scalars to 1D Array",
    icon="mdi-format-list-numbered",
    description="Collect up to 125 connected scalars in port order into a read-only 1D array.",
    requirements=("py:numpy",),
    ports=(
        PortDefinition(
            "scalar", PortDirection.INPUT, FLOAT, "Scalar", required=False, expandable=125
        ),
        PortDefinition("array", PortDirection.OUTPUT, ARRAY_1D, "Array"),
    ),
    executor=_scalars_to_array_1d,
)


def _extract_vector_value(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Return one real vector component without copying or modifying its storage."""
    vector = np.asarray(inputs["vector"])
    if vector.ndim != 1 or vector.size == 0:
        raise ValueError("Extract Vector Value requires a non-empty one-dimensional vector")
    if vector.dtype.kind not in "iuf":
        raise TypeError("Extract Vector Value requires real integer or floating-point values")
    index = inputs.get("index", parameters.get("index", 0))
    if isinstance(index, (bool, np.bool_)) or not isinstance(index, (int, np.integer)):
        raise TypeError("Extract Vector Value index must be an integer")
    index = int(index)
    if not -vector.size <= index < vector.size:
        raise IndexError(
            f"Extract Vector Value index {index} is out of range for vector length {vector.size}"
        )
    return {"value": float(vector[index])}


EXTRACT_VECTOR_VALUE = NodeDefinition(
    id="extract-vector-value",
    label="Extract Vector Value",
    icon="mdi-vector-point",
    description="Extract a scalar by zero-based index; negative indices count from the end.",
    requirements=("py:numpy",),
    ports=(
        PortDefinition("vector", PortDirection.INPUT, ARRAY_1D, "Vector"),
        PortDefinition("value", PortDirection.OUTPUT, FLOAT, "Value"),
    ),
    parameters=(ParameterDefinition("index", ParameterKind.INTEGER, "Index", 0, "0"),),
    executor=_extract_vector_value,
)


def _vector_statistics(
    inputs: Mapping[str, Any],
    _parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Evaluate only requested statistics; unused outputs are NaN or -1."""
    outputs = {
        "min": float("nan"),
        "min_index": -1,
        "max": float("nan"),
        "max_index": -1,
        "mean": float("nan"),
        "std": float("nan"),
    }
    connected = frozenset() if _exec_context is None else _exec_context.connected_output_ports
    if not connected.intersection(outputs):
        return outputs

    vector = np.asarray(inputs["vector"])
    if vector.ndim == 2 and vector.shape[1] == 1:
        vector = vector[:, 0]
    if vector.ndim != 1 or vector.size == 0:
        raise ValueError("Vector Statistics requires a non-empty one-dimensional vector")
    if vector.dtype.kind not in "iuf":
        raise TypeError("Vector Statistics requires real integer or floating-point values")
    if not np.all(np.isfinite(vector)):
        raise ValueError("Vector Statistics requires finite values")

    for name, reduce, locate in (("min", np.min, np.argmin), ("max", np.max, np.argmax)):
        index_name = f"{name}_index"
        if index_name in connected:
            index = int(locate(vector))
            outputs[index_name] = index
            if name in connected:
                outputs[name] = float(vector[index])
        elif name in connected:
            outputs[name] = float(reduce(vector))
    if "mean" in connected:
        outputs["mean"] = float(np.mean(vector, dtype=np.float64))
    if "std" in connected:
        outputs["std"] = float(np.std(vector, dtype=np.float64, ddof=0))
    return outputs


VECTOR_STATISTICS = NodeDefinition(
    id="vector-statistics",
    label="Vector Statistics",
    icon="mdi-chart-bell-curve",
    description="Compute connected vector statistics: extrema and indices, mean, and population std.",
    requirements=("py:numpy",),
    ports=(
        PortDefinition("vector", PortDirection.INPUT, ARRAY_1D, "Vector"),
        PortDefinition("min", PortDirection.OUTPUT, FLOAT, "Minimum"),
        PortDefinition("min_index", PortDirection.OUTPUT, INTEGER, "Minimum index"),
        PortDefinition("max", PortDirection.OUTPUT, FLOAT, "Maximum"),
        PortDefinition("max_index", PortDirection.OUTPUT, INTEGER, "Maximum index"),
        PortDefinition("mean", PortDirection.OUTPUT, FLOAT, "Mean"),
        PortDefinition("std", PortDirection.OUTPUT, FLOAT, "Standard deviation"),
    ),
    executor=_vector_statistics,
)

AVAILABLE_NODES = (SCALARS_TO_ARRAY_1D, EXTRACT_VECTOR_VALUE, VECTOR_STATISTICS)

__all__ = ["AVAILABLE_NODES", "EXTRACT_VECTOR_VALUE", "SCALARS_TO_ARRAY_1D", "VECTOR_STATISTICS"]
