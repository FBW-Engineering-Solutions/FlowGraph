"""Workflow nodes that read external data into FlowGraph domain objects."""

import logging
import xml.sax
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from flowgraph.application.workflow_core import (
    ExecContext,
    NodeDefinition,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
)
from flowgraph.domain.mesh_document import MeshDocument

from .data_types import ARRAY_1D, MESH_DOCUMENT, TABLE_DOCUMENT, ParameterKind
from .file_conversion import get_available_mesh_times

LOGGER = logging.getLogger(__name__)


"""Boundary between a source file and FlowGraph's canonical Muscat document."""


class MeshLoadError(RuntimeError):
    """Raised when a selected mesh cannot be loaded by a reader adapter."""


class TableReadError(RuntimeError):
    """Raised when a table document cannot be read by a reader adapter."""


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


def _validate_table_source(inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Path:
    """Return a usable table source path or raise a table-specific error."""
    configured_path = inputs.get("path", parameters.get("path", ""))
    source = Path(configured_path).expanduser()

    if not source.is_file():
        raise TableReadError(f"Table file does not exist or is not a file: {source}")
    return source


def _load_muscat(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Read temporal metadata and materialize the selected snapshot if requested."""
    from Muscat.MeshContainers.Mesh import Mesh

    source = _validate_source(inputs, parameters, "Muscat")
    requested = (
        {port.name for port in LOAD_MUSCAT.outputs}
        if _exec_context is None
        else _exec_context.connected_output_ports
    )
    want_mesh = "mesh" in requested
    want_times = "available_timesteps" in requested
    index = parameters.get("timestep_to_read", -1)
    # Legacy saved dropdown values still select the same single snapshot.
    if "timestep_to_read" not in inputs and isinstance(index, str):
        index = {"first": 0, "last": -1, "all": -1}.get(index, index)
    if want_mesh and (
        isinstance(index, (bool, np.bool_)) or not isinstance(index, (int, np.integer))
    ):
        raise MeshLoadError(f"Timestep to read must be an integer index, got {index!r}")
    document = None
    times = ()

    try:
        if want_mesh or want_times:
            from Muscat.IO.IOFactory import CreateReader, InitAllReaders
            from Muscat.IO.XdmfReader import XdmfReader

            InitAllReaders()
            reader = CreateReader(source.suffix)
            reader.SetFileName(str(source))
            grids = None
            if isinstance(reader, XdmfReader):
                # ReadMetaData calls Read(), which materializes a grid even in
                # lazy mode. Parse with Muscat's SAX handler without GetSupport.
                reader.Reset()
                reader.lazy = True
                if not want_mesh:
                    # Ignore inline DataItem payloads; time values are attributes.
                    reader.characters = lambda _content: None
                parser = xml.sax.make_parser()
                parser.setContentHandler(reader)
                parser.setFeature(xml.sax.handler.feature_external_ges, False)
                with source.open("rb") as stream:
                    parser.parse(stream)
                grids = [grid for grid in reader.xdmf.GetDomain(0).grids if grid.time is not None]
                times = [grid.GetTime() for grid in grids]
            elif want_mesh:
                times = get_available_mesh_times(reader)
            else:
                times = _muscat_times_only(reader)

            if want_mesh:
                count = max(1, len(times))
                if not -count <= int(index) < count:
                    raise ValueError(f"Time-step index {index} out of range for {count} snapshots")
                index = int(index) % count
                if len(times) == 0:
                    mesh = (
                        reader.Read()
                        if grids is None
                        else reader.xdmf.GetDomain(-1).GetGrid(-1).GetSupport()
                    )
                    document = MeshDocument(mesh=mesh.View())
                else:
                    if grids is not None:
                        mesh = grids[index].GetSupport()
                    else:
                        reader.SetTimeToRead(None, timeIndex=index)
                        mesh = reader.Read()
                    document = MeshDocument(mesh=mesh.View())
    except Exception as error:
        LOGGER.exception("Muscat failed while loading %s", source)
        raise MeshLoadError(f"Muscat could not load '{source}': {error}") from error

    available = np.asarray(times if want_times and len(times) else (0.0,), dtype=float).view()
    available.flags.writeable = False
    return {
        "mesh": document if document is not None else MeshDocument(mesh=Mesh()),
        "available_timesteps": available,
    }


def _muscat_times_only(reader: Any) -> Any:
    """Avoid backends' mesh-related metadata work when only times are requested."""
    from Muscat.IO.RstReader import RstReader
    from Muscat.IO.UtReader import UtReader

    if isinstance(reader, UtReader):
        reader.ReadUTMetaData()
        return reader.GetAvailableTimes() if len(reader.time) else ()
    if isinstance(reader, RstReader):
        return reader.GetModel().metadata.time_freq_support.time_frequencies.data
    return get_available_mesh_times(reader)


def _load_meshio(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
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


def _load_meshlane(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
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


def load_csv(
    inputs: Mapping[str, Any],
    _parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
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


def _read_table(
    inputs: Mapping[str, Any],
    parameters: Mapping[str, Any],
    _exec_context: ExecContext | None = None,
) -> Mapping[str, Any]:
    """Read an Excel workbook into the canonical table-document mapping."""
    source = _validate_table_source(inputs, parameters)
    sheet_name = parameters.get("sheet_name", "Sheet1")

    try:
        import pandas as pd

        dataframe = pd.read_excel(source, sheet_name=sheet_name)
        data = dataframe.to_dict(orient="list")
    except Exception as error:
        LOGGER.exception("Pandas failed while reading %s", source)
        raise TableReadError(f"Pandas could not read '{source}': {error}") from error

    LOGGER.info("Pandas read table document from %s", source.resolve())
    return {"data": data}


LOAD_MUSCAT = NodeDefinition(
    id="load-muscat",
    requirements=("py:muscat",),
    icon="/__flowgraph_ui/LOAD_MUSCAT.svg",
    label="Read Mesh (Muscat)",
    description=(
        "Loads a mesh by time-step index (0 is first, -1 is last). "
        "Lists available time steps without loading snapshots when only that output is used. "
        "Companion changes must update the principal file timestamp."
    ),
    ports=(
        PortDefinition("mesh", PortDirection.OUTPUT, MESH_DOCUMENT, "Mesh"),
        PortDefinition(
            "available_timesteps", PortDirection.OUTPUT, ARRAY_1D, "Available Time Steps"
        ),
    ),
    executor=_load_muscat,
    parameters=(
        ParameterDefinition(
            "path", ParameterKind.FILE, "File path", "", "/path/to/mesh", port=True
        ),
        ParameterDefinition(
            "timestep_to_read",
            ParameterKind.INTEGER,
            "Timestep to read",
            -1,
            "-1",
            port=True,
        ),
    ),
)


LOAD_MESHIO = NodeDefinition(
    id="load-meshio",
    requirements=("py:muscat", "py:meshio"),
    icon="/__flowgraph_ui/LOAD_MESHIO.svg",
    label="Read Mesh (MeshIO)",
    description="Loads a file with meshio through Muscat's meshio bridge. Companion changes must update the principal file timestamp.",
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
    requirements=("py:muscat", "py:meshlane"),
    icon="/__flowgraph_ui/LOAD_MESHLANE.svg",
    label="Read Mesh (MeshLane)",
    description="Loads a file with the optional MeshLane adapter. Companion changes must update the principal file timestamp.",
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
    requirements=("py:pandas", "py:numpy"),
    icon="mdi-file-table-outline",
    label="Read Table (Pandas)",
    description="Loads a csv file with the optional Panda adapter.",
    ports=(PortDefinition("table", PortDirection.OUTPUT, TABLE_DOCUMENT, "Table"),),
    parameters=(
        ParameterDefinition(
            "path", ParameterKind.FILE, "File path", "", "/path/to/csvfile", port=True
        ),
    ),
    executor=load_csv,
)


READ_TABLE = NodeDefinition(
    id="read-table",
    requirements=("py:pandas", "py:openpyxl"),
    icon="mdi-file-table-outline",
    label="Read Table (Pandas)",
    description="Reads an Excel workbook into a table document with pandas.",
    ports=(PortDefinition("data", PortDirection.OUTPUT, TABLE_DOCUMENT, "Data"),),
    executor=_read_table,
    parameters=(
        ParameterDefinition(
            "path",
            ParameterKind.FILE,
            "File path",
            "input_pandas.xlsx",
            "/path/to/input.xlsx",
            file_patterns=("*.xlsx",),
        ),
        ParameterDefinition(
            "sheet_name", ParameterKind.TEXT, "Sheet name", "Sheet1", "Sheet1_name"
        ),
    ),
)
