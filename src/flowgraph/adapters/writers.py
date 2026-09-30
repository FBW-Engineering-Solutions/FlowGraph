"""Workflow nodes that write FlowGraph domain objects to external files."""

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from flowgraph.adapters.readers import MESH_DOCUMENT
from flowgraph.application.workflow_core import (
    ExecContext,
    NodeDefinition,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
)
from flowgraph.domain.mesh_document import MeshDocument

from .data_types import TABLE_DOCUMENT, ParameterKind

LOGGER = logging.getLogger(__name__)


class MeshWriteError(RuntimeError):
    """Raised when a mesh document cannot be written by a writer adapter."""


class TableWriteError(RuntimeError):
    """Raised when a table document cannot be written by a writer adapter."""


def _validate_destination(
    inputs: Mapping[str, Any], parameters: Mapping[str, Any], writer_name: str
) -> Path:
    """Return a usable destination or raise a writer-specific error."""
    configured_path = inputs.get("path", parameters.get("path", ""))
    destination = Path(configured_path).expanduser()

    if not destination.name:
        raise MeshWriteError("Mesh filename must not be empty")
    if not destination.suffix:
        raise MeshWriteError(
            f"Mesh filename has no extension; {writer_name} cannot select a writer: {destination}"
        )
    if not destination.parent.is_dir():
        raise MeshWriteError(
            f"Mesh output directory does not exist or is not a directory: {destination.parent}"
        )
    return destination


def _write_muscat(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Write a mesh document using Muscat's extension-aware universal writer."""

    destination = _validate_destination(inputs, parameters, "Muscat")
    document: MeshDocument = inputs["mesh"]

    try:
        from Muscat.IO.UniversalWriter import InitAllWriters, WriteMesh

        LOGGER.debug("Initialising Muscat writers for %s", destination)
        InitAllWriters()
        LOGGER.info("Writing mesh document with Muscat: %s", destination)
        WriteMesh(destination, document.mesh)
    except Exception as error:
        LOGGER.exception("Muscat failed while writing %s", destination)
        raise MeshWriteError(f"Muscat could not write '{destination}': {error}") from error

    LOGGER.info("Muscat wrote mesh document to %s", destination.resolve())
    return {}


def _write_meshio(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Convert a Muscat mesh through its meshio bridge and write it with meshio."""
    destination = _validate_destination(inputs, parameters, "meshio")
    document: MeshDocument = inputs["mesh"]

    try:
        import meshio
        from Muscat.Bridges.MeshIOBridge import MeshToMeshIO

        LOGGER.info("Writing mesh document with meshio: %s", destination)
        meshio.write(destination, MeshToMeshIO(document.mesh))
    except Exception as error:
        LOGGER.exception("meshio failed while writing %s", destination)
        raise MeshWriteError(f"meshio could not write '{destination}': {error}") from error

    LOGGER.info("meshio wrote mesh document to %s", destination.resolve())
    return {}


def _write_meshlane(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Convert a Muscat mesh and write it with the optional MeshLane adapter."""
    destination = _validate_destination(inputs, parameters, "MeshLane")
    document: MeshDocument = inputs["mesh"]

    try:
        import meshlane
    except ImportError as error:
        raise MeshWriteError(
            "MeshLane is not installed; install FlowGraph with the 'meshlane' extra"
        ) from error

    try:
        from Muscat.Bridges.MeshlaneBridge import MeshToMeshlane
    except ImportError as error:
        raise MeshWriteError(
            "This Muscat installation has no MeshLane bridge; install FlowGraph with "
            "the 'meshlane' extra"
        ) from error

    try:
        LOGGER.info("Writing mesh document with MeshLane: %s", destination)
        meshlane.write(destination, MeshToMeshlane(document.mesh))
    except Exception as error:
        LOGGER.exception("MeshLane failed while writing %s", destination)
        raise MeshWriteError(f"MeshLane could not write '{destination}': {error}") from error

    LOGGER.info("MeshLane wrote mesh document to %s", destination.resolve())
    return {}


def _write_table(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Write a table document to an Excel workbook with pandas."""
    configured_path = inputs.get("path", parameters.get("path", "output_pandas.xlsx"))
    destination = Path(configured_path).expanduser()
    if not destination.name:
        raise TableWriteError("Table filename must not be empty")
    if not destination.parent.is_dir():
        raise TableWriteError(
            f"Table output directory does not exist or is not a directory: {destination.parent}"
        )

    data = inputs["data"]
    if not isinstance(data, Mapping):
        raise TableWriteError("Table data must be a mapping of column names to values")

    sheet_name = parameters.get("sheet_name", "Sheet1")
    header = parameters.get("header", True)

    try:
        import pandas as pd

        dataframe = pd.DataFrame(data)
        dataframe.to_excel(
            destination,
            index=False,
            sheet_name=sheet_name,
            header=header,
        )
    except Exception as error:
        LOGGER.exception("Pandas failed while writing %s", destination)
        raise TableWriteError(f"Pandas could not write '{destination}': {error}") from error

    LOGGER.info("Pandas wrote table document to %s", destination.resolve())
    return {}


WRITE_MUSCAT = NodeDefinition(
    id="write-muscat",
    requirements=("py:muscat",),
    icon="mdi-file-export-outline",
    label="Write Mesh (Muscat)",
    description="Writes the canonical mesh document to a filename selected by extension.",
    ports=(PortDefinition("mesh", PortDirection.INPUT, MESH_DOCUMENT, "Mesh"),),
    executor=_write_muscat,
    parameters=(
        ParameterDefinition(
            "path", ParameterKind.FILE, "File path", "", "/path/to/mesh", port=True
        ),
    ),
)


WRITE_MESHIO = NodeDefinition(
    id="write-meshio",
    requirements=("py:muscat", "py:meshio"),
    icon="mdi-file-swap-outline",
    label="Write Mesh (MeshIO)",
    description="Writes the canonical mesh document with meshio through Muscat's bridge.",
    ports=(PortDefinition("mesh", PortDirection.INPUT, MESH_DOCUMENT, "Mesh"),),
    executor=_write_meshio,
    parameters=(
        ParameterDefinition(
            "path", ParameterKind.FILE, "File path", "", "/path/to/mesh", port=True
        ),
    ),
)


WRITE_MESHLANE = NodeDefinition(
    id="write-meshlane",
    requirements=("py:muscat", "py:meshlane"),
    icon="mdi-file-swap-outline",
    label="Write Mesh (MeshLane)",
    description="Writes the canonical mesh document with the optional MeshLane adapter.",
    ports=(PortDefinition("mesh", PortDirection.INPUT, MESH_DOCUMENT, "Mesh"),),
    executor=_write_meshlane,
    parameters=(
        ParameterDefinition(
            "path", ParameterKind.FILE, "File path", "", "/path/to/mesh", port=True
        ),
    ),
)


WRITE_TABLE = NodeDefinition(
    id="write-table",
    requirements=("py:pandas", "py:openpyxl"),
    icon="mdi-file-table-outline",
    label="Write Table (Pandas)",
    description="Writes a table document to an Excel workbook with pandas.",
    ports=(PortDefinition("data", PortDirection.INPUT, TABLE_DOCUMENT, "Data"),),
    executor=_write_table,
    parameters=(
        ParameterDefinition(
            "path",
            ParameterKind.FILE,
            "File path",
            "output_pandas.xlsx",
            "/path/to/output.xlsx",
            file_patterns=("*.xlsx",),
        ),
        ParameterDefinition(
            "sheet_name", ParameterKind.TEXT, "Sheet name", "Sheet1", "Sheet1_name"
        ),
        ParameterDefinition("header", ParameterKind.BOOLEAN, "Header", True, port=False),
    ),
)
