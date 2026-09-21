"""Workflow nodes backed by the Plaid external dataset library."""

from collections.abc import Mapping
from typing import Any

from flowgraph.application.workflow_core import (
    DataType,
    NodeDefinition,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
)
from flowgraph.domain.mesh_document import MeshDocument

from .data_types import MESH_DOCUMENT, ParameterKind

PLAID_SAMPLE = DataType("plaid-dataset", "Plaid sample", object)
PLAID_INFO = DataType("plaid-info", "Plaid info", object)
PLAID_DATA_PRODUCTION = DataType("plaid-data-production", "Plaid data production", object)
PLAID_OPTIONAL_STRING = DataType("plaid-optional-string", "Optional Text", (str, type(None)))
PLAID_OPTIONAL_TABLE = DataType("plaid-optional-table", "Optional Table", (dict, type(None)))


def _load_plaid_sample(
    _inputs: Mapping[str, Any], parameters: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Load one sample from a Plaid dataset stored on disk."""
    path = parameters.get("path", "")

    if not isinstance(path, str) or not path:
        raise ValueError("The Plaid dataset path must be a non-empty string")

    try:
        from plaid.storage.reader import init_from_disk, load_infos_from_disk
    except ImportError as error:
        raise RuntimeError(
            "The Plaid library is required to load Plaid samples; "
            "install the package providing plaid.storage.reader. "
            "> uv pip install pyplaid"
        ) from error

    infos = load_infos_from_disk(path)
    datasetdict, converterdict = init_from_disk(path)

    return {"dataset": (datasetdict, converterdict), "infos": infos}


LOAD_PLAID_DATASET = NodeDefinition(
    id="load-plaid-dataset",
    icon="mdi-database-arrow-down-outline",
    label="Load Plaid Dataset",
    description="Loads dataset from a Plaid dataset on disk.",
    ports=(
        PortDefinition("dataset", PortDirection.OUTPUT, PLAID_SAMPLE, "Sample"),
        PortDefinition("infos", PortDirection.OUTPUT, PLAID_INFO, "Infos"),
    ),
    executor=_load_plaid_sample,
    parameters=(ParameterDefinition("path", ParameterKind.FILE, "Path", "", "/path/to/plaid"),),
)


def _extract_plaid_sample(
    inputs: Mapping[str, Any], parameters: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Convert one stored Plaid dataset item into a Plaid ``Sample``."""
    dataset_and_converters = inputs.get("dataset")
    infos = inputs.get("infos")
    split = parameters.get("split", "")
    sample_number = parameters.get("sample_number", 0)

    if (
        not isinstance(dataset_and_converters, tuple)
        or len(dataset_and_converters) != 2
        or not isinstance(dataset_and_converters[0], Mapping)
        or not isinstance(dataset_and_converters[1], Mapping)
    ):
        raise TypeError("The PLAID_SAMPLE input must contain dataset and converter mappings")
    if infos is None:
        raise ValueError("The PLAID_INFO input is required")
    if not isinstance(split, str) or not split:
        raise ValueError("The Plaid split must be a non-empty string")
    if isinstance(sample_number, bool) or not isinstance(sample_number, int):
        raise TypeError("The Plaid sample number must be an integer")
    if sample_number < 0:
        raise ValueError("The Plaid sample number must not be negative")

    datasetdict, converterdict = dataset_and_converters
    try:
        dataset = datasetdict[split]
        converter = converterdict[split]
        sample = converter.to_plaid(dataset, sample_number)
    except (KeyError, IndexError, TypeError, ValueError, OSError) as error:
        raise ValueError(
            f"Could not extract Plaid sample: split={split!r}, sample_number={sample_number}"
        ) from error

    return {"sample": sample}


EXTRACT_PLAID_SAMPLE = NodeDefinition(
    id="extract-plaid-sample",
    icon="mdi-database-search-outline",
    label="Extract Plaid sample",
    description="Converts one item from a loaded Plaid dataset into a Plaid Sample.",
    ports=(
        PortDefinition("dataset", PortDirection.INPUT, PLAID_SAMPLE, "PLAID_SAMPLE"),
        PortDefinition("infos", PortDirection.INPUT, PLAID_INFO, "PLAID_INFO"),
        PortDefinition("sample", PortDirection.OUTPUT, PLAID_SAMPLE, "Sample"),
    ),
    executor=_extract_plaid_sample,
    parameters=(
        ParameterDefinition("split", ParameterKind.TEXT, "Split", "", "train"),
        ParameterDefinition("sample_number", ParameterKind.INTEGER, "Sample number", 0, "0"),
    ),
)


def _extract_plaid_time_step(
    inputs: Mapping[str, Any], parameters: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Extract one Plaid sample time step as a FlowGraph mesh document."""
    sample = inputs.get("sample")
    time = parameters.get("time", 0.0)

    if sample is None:
        raise ValueError("The PLAID_SAMPLE input is required")
    if isinstance(time, bool) or not isinstance(time, (int, float)):
        raise TypeError("The Plaid time step must be numeric")

    try:
        from Muscat.Bridges.CGNSBridge import CGNSToMesh

        tree = sample.get_tree(time=float(time), only_mesh=False)
        if tree is None:
            raise ValueError(f"Plaid sample has no mesh at time step {time}")
        mesh = CGNSToMesh(tree)
        return {"mesh": MeshDocument(mesh=mesh)}
    except (AttributeError, TypeError, ValueError, IndexError, KeyError) as error:
        raise ValueError(f"Could not extract Plaid time step {time}: {error}") from error


EXTRACT_PLAID_TIME_STEP = NodeDefinition(
    id="extract-plaid-time-step",
    icon="mdi-calendar-clock-outline",
    label="Extract Plaid time step",
    description="Converts one Plaid sample time step into a FlowGraph mesh document.",
    ports=(
        PortDefinition("sample", PortDirection.INPUT, PLAID_SAMPLE, "PLAID_SAMPLE"),
        PortDefinition("mesh", PortDirection.OUTPUT, MESH_DOCUMENT, "Mesh"),
    ),
    executor=_extract_plaid_time_step,
    parameters=(ParameterDefinition("time", ParameterKind.FLOAT, "Time step", 0.0, "0.0"),),
)


def _extract_plaid_info(
    inputs: Mapping[str, Any], _parameters: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Expose each top-level attribute of a Plaid ``Infos`` object."""
    infos = inputs.get("infos")
    if infos is None:
        raise ValueError("The PLAID_INFO input is required")

    return {
        "owner": getattr(infos, "owner", None),
        "license": getattr(infos, "license", None),
        "data_production": getattr(infos, "data_production", None),
        "data_description": getattr(infos, "data_description", None),
        "num_samples": getattr(infos, "num_samples", None),
        "storage_backend": getattr(infos, "storage_backend", None),
    }


EXTRACT_PLAID_INFO = NodeDefinition(
    id="extract-plaid-info",
    icon="mdi-information-outline",
    label="Extract Plaid info",
    description="Exposes the top-level attributes of a Plaid dataset info object.",
    ports=(
        PortDefinition("infos", PortDirection.INPUT, PLAID_INFO, "PLAID_INFO"),
        PortDefinition("owner", PortDirection.OUTPUT, PLAID_OPTIONAL_STRING, "Owner"),
        PortDefinition("license", PortDirection.OUTPUT, PLAID_OPTIONAL_STRING, "License"),
        PortDefinition(
            "data_production", PortDirection.OUTPUT, PLAID_DATA_PRODUCTION, "Data production"
        ),
        PortDefinition(
            "data_description", PortDirection.OUTPUT, PLAID_OPTIONAL_STRING, "Data description"
        ),
        PortDefinition(
            "num_samples", PortDirection.OUTPUT, PLAID_OPTIONAL_TABLE, "Number of samples"
        ),
        PortDefinition(
            "storage_backend", PortDirection.OUTPUT, PLAID_OPTIONAL_STRING, "Storage backend"
        ),
    ),
    executor=_extract_plaid_info,
)


AVAILABLE_NODES = (
    LOAD_PLAID_DATASET,
    EXTRACT_PLAID_SAMPLE,
    EXTRACT_PLAID_TIME_STEP,
    EXTRACT_PLAID_INFO,
)
