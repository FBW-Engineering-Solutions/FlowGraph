"""Demand-driven statistics for one-dimensional numeric data."""

from collections.abc import Mapping
from typing import Any

import numpy as np

from flowgraph.application.workflow_core import (
    ExecContext,
    NodeDefinition,
    PortDefinition,
    PortDirection,
)

from .data_types import ANY, FLOAT, INTEGER


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
        PortDefinition("vector", PortDirection.INPUT, ANY, "Vector"),
        PortDefinition("min", PortDirection.OUTPUT, FLOAT, "Minimum"),
        PortDefinition("min_index", PortDirection.OUTPUT, INTEGER, "Minimum index"),
        PortDefinition("max", PortDirection.OUTPUT, FLOAT, "Maximum"),
        PortDefinition("max_index", PortDirection.OUTPUT, INTEGER, "Maximum index"),
        PortDefinition("mean", PortDirection.OUTPUT, FLOAT, "Mean"),
        PortDefinition("std", PortDirection.OUTPUT, FLOAT, "Standard deviation"),
    ),
    executor=_vector_statistics,
)

AVAILABLE_NODES = (VECTOR_STATISTICS,)

__all__ = ["AVAILABLE_NODES", "VECTOR_STATISTICS"]
