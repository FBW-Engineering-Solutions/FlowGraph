"""Workflow nodes that read external data into FlowGraph domain objects."""

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from flowgraph.application.workflow_core import (
    NodeDefinition,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
)
from flowgraph.domain.mesh_document import MeshDocument

from .data_types import MESH_DOCUMENT, STRING, TABLE_DOCUMENT, ParameterKind

LOGGER = logging.getLogger(__name__)


"""Boundary between a source file and FlowGraph's canonical Muscat document."""


class MeshLoadError(RuntimeError):
    """Raised when a selected mesh cannot be loaded by a reader adapter."""


def _validate_source(
    inputs: Mapping[str, Any], parameters: Mapping[str, Any], reader_name: str
) -> Path:
    """Return a usable source path or raise a reader-specific load error."""
    configured_path = inputs.get("path", parameters.get("path", ""))
    source = Path(configured_path).expanduser()

    LOGGER.debug("Validating requested mesh path: %s", source)
    if not source.is_file():
        LOGGER.warning("Rejected missing/non-file mesh path: %s", source)
        raise MeshLoadError(f"Mesh file does not exist or is not a file: {source}")
    if not source.suffix:
        LOGGER.warning("Rejected extensionless mesh path: %s", source)
        raise MeshLoadError(
            f"Mesh file has no extension; {reader_name} cannot select a reader: {source}"
        )
    return source


def _load_muscat(inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Load *source* with Muscat's extension-aware universal mesh reader.

    The returned :class:`~flowgraph.domain.mesh_document.MeshDocument` is the
    canonical editable model. The caller can display its summary immediately;
    VTK conversion remains a separate, derived projection.
    """

    source = _validate_source(inputs, parameters, "Muscat")

    try:
        from Muscat.IO.IOFactory import CreateReader, InitAllReaders

        LOGGER.debug("Initialising Muscat readers for %s", source)
        InitAllReaders()
        reader = CreateReader(source.suffix)
        LOGGER.info("Loading mesh with Muscat reader %s: %s", type(reader).__name__, source)
        reader.SetFileName(str(source))
        mesh = reader.Read()
    except Exception as error:
        LOGGER.exception("Muscat failed while loading %s", source)
        raise MeshLoadError(f"Muscat could not load '{source}': {error}") from error

    LOGGER.info(
        "Muscat loaded %s (%d nodes, %d elements)",
        source,
        mesh.GetNumberOfNodes(),
        mesh.GetNumberOfElements(),
    )
    return {"mesh": MeshDocument(mesh=mesh)}


def _load_meshio(inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Load *source* with meshio and convert it through Muscat's bridge."""
    source = _validate_source(inputs, parameters, "meshio")

    try:
        import meshio
        from Muscat.Bridges.MeshIOBridge import MeshIOToMesh

        LOGGER.info("Loading mesh with meshio: %s", source)
        mesh = MeshIOToMesh(meshio.read(source))
    except Exception as error:
        LOGGER.exception("meshio failed while loading %s", source)
        raise MeshLoadError(f"meshio could not load '{source}': {error}") from error

    LOGGER.info(
        "meshio loaded %s through the Muscat bridge (%d nodes, %d elements)",
        source,
        mesh.GetNumberOfNodes(),
        mesh.GetNumberOfElements(),
    )
    return {"mesh": MeshDocument(mesh=mesh)}


def _load_meshlane(inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Load *source* with the optional MeshLane adapter."""
    source = _validate_source(inputs, parameters, "MeshLane")

    try:
        import meshlane
    except ImportError as error:
        raise MeshLoadError(
            "MeshLane is not installed; install FlowGraph with the 'meshlane' extra"
        ) from error

    try:
        from Muscat.Bridges.MeshlaneBridge import MeshlaneToMesh
    except ImportError as error:
        raise MeshLoadError(
            "This Muscat installation has no MeshLane bridge; install FlowGraph with "
            "the 'meshlane' extra"
        ) from error

    try:
        LOGGER.info("Loading mesh with MeshLane: %s", source)
        mesh = MeshlaneToMesh(meshlane.read(source))
    except Exception as error:
        LOGGER.exception("MeshLane failed while loading %s", source)
        raise MeshLoadError(f"MeshLane could not load '{source}': {error}") from error

    LOGGER.info(
        "MeshLane loaded %s through the Muscat bridge (%d nodes, %d elements)",
        source,
        mesh.GetNumberOfNodes(),
        mesh.GetNumberOfElements(),
    )
    return {"mesh": MeshDocument(mesh=mesh)}


def load_csv(inputs: Mapping[str, Any], _parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """
    Load a CSV file and return a dictionary where the keys are column names and the values are numpy arrays.

    Args:
        file_path (str): The path to the CSV file.

    Returns:
        dict: A dictionary where the keys are column names and the values are numpy arrays.
    """
    import pandas as pd

    # Read the CSV file
    source = _validate_source(inputs, {}, "MeshLane")
    df = pd.read_csv(source)

    # Convert the DataFrame to a dictionary
    data_dict = {col: df[col].to_numpy() for col in df.columns}

    # Return the dictionary
    return {"table": data_dict}


LOAD_MUSCAT = NodeDefinition(
    id="load-muscat",
    icon="/__flowgraph_ui/LOAD_MUSCAT.svg",
    label="Read Mesh (Muscat)",
    description="Loads a file path into the canonical mesh document.",
    ports=(PortDefinition("mesh", PortDirection.OUTPUT, MESH_DOCUMENT, "Mesh"),),
    executor=_load_muscat,
    parameters=(
        ParameterDefinition(
            "path", ParameterKind.FILE, "File path", "", "/path/to/mesh", port=True
        ),
    ),
)


LOAD_MESHIO = NodeDefinition(
    id="load-meshio",
    icon="/__flowgraph_ui/LOAD_MESHIO.svg",
    label="Read Mesh (MeshIO)",
    description="Loads a file with meshio through Muscat's meshio bridge.",
    ports=(PortDefinition("mesh", PortDirection.OUTPUT, MESH_DOCUMENT, "Mesh"),),
    executor=_load_meshio,
    parameters=(
        ParameterDefinition(
            "path", ParameterKind.FILE, "File path", "", "/path/to/mesh", port=True
        ),
    ),
)


LOAD_MESHLANE = NodeDefinition(
    id="load-meshlane",
    icon="/__flowgraph_ui/LOAD_MESHLANE.svg",
    label="Read Mesh (MeshLane)",
    description="Loads a file with the optional MeshLane adapter.",
    ports=(PortDefinition("mesh", PortDirection.OUTPUT, MESH_DOCUMENT, "Mesh"),),
    executor=_load_meshlane,
    parameters=(
        ParameterDefinition(
            "path", ParameterKind.FILE, "File path", "", "/path/to/mesh", port=True
        ),
    ),
)


LOAD_CSV = NodeDefinition(
    id="load-csv",
    icon="mdi-file-table-outline",
    label="Read Table (Pandas)",
    description="Loads a csv file with the optional Panda adapter.",
    ports=(
        PortDefinition("path", PortDirection.INPUT, STRING, "File path"),
        PortDefinition("table", PortDirection.OUTPUT, TABLE_DOCUMENT, "Table"),
    ),
    executor=load_csv,
)
