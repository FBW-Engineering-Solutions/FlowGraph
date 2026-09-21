"""Workflow node for converting mesh files between supported formats."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar

from flowgraph.application.workflow_core import (
    NodeDefinition,
    ParameterDefinition,
    ParameterOption,
    PortDefinition,
    PortDirection,
)

from .data_types import FILE, ParameterKind


class MeshFileConversionError(RuntimeError):
    """Raised when a mesh file conversion cannot be completed."""


class DelayInitialization:
    """Lazily resolve the reader or writer classes in a conversion catalog."""

    _namespace: ClassVar[dict[str, Any]] = {}

    def __init__(self, delayed_init_struct: Mapping[str, str]) -> None:
        self.entries: dict[str, type[Any]] = {}
        self.delayed_init_struct = dict(delayed_init_struct)

    def __getitem__(self, key: str) -> type[Any]:
        """Return the class registered under *key*, importing it on first use."""
        if key not in self.delayed_init_struct:
            raise KeyError(f"Unknown conversion format: {key!r}")
        if key in self.entries:
            return self.entries[key]

        namespace: dict[str, Any] = {}
        try:
            exec(self.delayed_init_struct[key], self._namespace, namespace)  # noqa: S102
            resolved = namespace.get("res")
        except Exception as error:
            raise MeshFileConversionError(
                f"Could not initialize conversion format {key!r}: {error}"
            ) from error

        if not isinstance(resolved, type):
            raise MeshFileConversionError(f"Conversion format {key!r} did not resolve to a class")
        self.entries[key] = resolved
        return resolved

    def keys(self):
        """Return the available conversion format keys."""
        return self.delayed_init_struct.keys()

    def check(self) -> None:
        """Resolve every registered class and raise the first import error."""
        for key in self.delayed_init_struct:
            try:
                self[key]
            except Exception as error:
                raise RuntimeError(
                    f"Could not initialize conversion format {key}",
                ) from error

    def get_class(self, filename: str | Path, key: str) -> type[Any]:
        """Return an explicitly selected or extension-selected conversion class."""
        if key == "auto":
            suffixes = Path(filename).suffixes
            extension = "".join(suffixes[-2:]).lower() if len(suffixes) > 1 else ""
            extension = extension or Path(filename).suffix.lower()
            muscat_obj = None
            other_obj = None
            for candidate in self.delayed_init_struct:
                rext, backend, *_ = candidate.split(" ")
                if extension == rext and other_obj is None:
                    other_obj = candidate
                if extension == rext and muscat_obj is None and backend == "Muscat":
                    muscat_obj = candidate
                    break
            selected = muscat_obj or other_obj
            if selected is None:
                raise MeshFileConversionError(
                    f"No conversion class is registered for extension {extension!r}"
                )
            return self[selected]
        return self[key]

    GetClass = get_class


ReaderDelayedInitStruct = {
    ".ans Muscat FemmReader": "from Muscat.IO.FemmReader import FemmReader; res = FemmReader",
    ".ansys Muscat AnsysReader": "from Muscat.IO.AnsysReader import AnsysReader; res = AnsysReader",
    ".asc Muscat AscReader": "from Muscat.IO.AscReader import AscReader; res = AscReader",
    ".avs MeshIO avs_avsucd_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_avs_avsucd_Reader; res = MeshIO_avs_avsucd_Reader",
    ".bdf MeshIO bdf_nastran_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_bdf_nastran_Reader; res = MeshIO_bdf_nastran_Reader",
    ".cgns MeshIO cgns_cgns_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_cgns_cgns_Reader; res = MeshIO_cgns_cgns_Reader",
    ".cgns Muscat CGNSReader": "from Muscat.IO.CGNSReader import CGNSReader; res = CGNSReader",
    ".dat MeshIO dat_tecplot_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_dat_tecplot_Reader; res = MeshIO_dat_tecplot_Reader",
    ".dat Muscat DatReader": "from Muscat.IO.SamcefReader import DatReader;res = DatReader",
    ".dato MeshIO dato_permas_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_dato_permas_Reader; res = MeshIO_dato_permas_Reader",
    ".dato.gz MeshIO dato.gz_permas_Reader": """from Muscat.Bridges.MeshIOBridge import readers; res = readers["MeshIO_dato.gz_permas_Reader"]""",
    ".datt Muscat DatReader": "from Muscat.IO.SamcefReader import DatReader; res = DatReader",
    ".dill Muscat DillReader": "from Muscat.IO.DillTools import DillReader; res = DillReader",
    ".ele MeshIO ele_tetgen_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_ele_tetgen_Reader; res = MeshIO_ele_tetgen_Reader",
    ".f3grid MeshIO f3grid_flac3d_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_f3grid_flac3d_Reader; res = MeshIO_f3grid_flac3d_Reader",
    ".fac Muscat SamcefOuputReader": "from Muscat.IO.SamcefOutputReader import SamcefOuputReader; res = SamcefOuputReader ",
    ".fem MeshIO fem_nastran_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_fem_nastran_Reader; res = MeshIO_fem_nastran_Reader",
    ".fem Muscat FemReader": "from Muscat.IO.FemReader import FemReader; res = FemReader",
    ".gcode Muscat GReader": "from Muscat.IO.GReader import GReader; res = GReader",
    ".geo Muscat GeoReader": "from Muscat.IO.GeoReader import GeoReader; res =GeoReader",
    ".geof Muscat GeofReader": "from Muscat.IO.GeofReader import GeofReader; res = GeofReader",
    ".h5m MeshIO h5m_h5m_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_h5m_h5m_Reader; res = MeshIO_h5m_h5m_Reader",
    ".inp MeshIO inp_abaqus_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_inp_abaqus_Reader; res = MeshIO_inp_abaqus_Reader",
    ".inp Muscat InpReader": "from Muscat.IO.InpReader import InpReader; res=InpReader",
    ".mdpa MeshIO mdpa_mdpa_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_mdpa_mdpa_Reader; res = MeshIO_mdpa_mdpa_Reader",
    ".med MeshIO med_med_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_med_med_Reader; res = MeshIO_med_med_Reader",
    ".mesh MeshIO mesh_medit_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_mesh_medit_Reader; res = MeshIO_mesh_medit_Reader",
    ".mesh Muscat MeshReader": "from Muscat.IO.MeshReader import MeshReader; res = MeshReader",
    ".meshb MeshIO meshb_medit_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_meshb_medit_Reader; res = MeshIO_meshb_medit_Reader",
    ".meshb Muscat MeshReader": "from Muscat.IO.MeshReader import MeshReader; res = MeshReader",
    ".msh MeshIO msh_ansys_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_msh_ansys_Reader; res = MeshIO_msh_ansys_Reader",
    ".msh MeshIO msh_gmsh_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_msh_gmsh_Reader; res = MeshIO_msh_gmsh_Reader",
    ".msh Muscat GmshReader": "from Muscat.IO.GmshReader import GmshReader; res = GmshReader",
    ".nas MeshIO nas_nastran_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_nas_nastran_Reader; res = MeshIO_nas_nastran_Reader",
    ".node MeshIO node_tetgen_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_node_tetgen_Reader; res = MeshIO_node_tetgen_Reader",
    ".obj MeshIO obj_obj_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_obj_obj_Reader; res = MeshIO_obj_obj_Reader",
    ".off MeshIO off_off_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_off_off_Reader; res = MeshIO_off_off_Reader",
    ".pickle Muscat PickleReader": "from Muscat.IO.PickleTools import PickleReader; res = PickleReader",
    ".ply MeshIO ply_ply_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_ply_ply_Reader; res = MeshIO_ply_ply_Reader",
    ".post MeshIO post_permas_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_post_permas_Reader; res = MeshIO_post_permas_Reader",
    ".post.gz MeshIO post.gz_permas_Reader": """from Muscat.Bridges.MeshIOBridge import readers; res = readers['MeshIO_post.gz_permas_Reader']""",
    ".pxdmf Muscat XdmfReader": "from Muscat.IO.XdmfReader import XdmfReader; res = XdmfReader",
    ".sdb Muscat SamcefOutputBaconReader": "from Muscat.IO.SamcefOutputReader import SamcefOutputBaconReader; res = SamcefOutputBaconReader",
    ".sol Muscat MeshSolutionReaderWrapper": "from Muscat.IO.MeshReader import  MeshSolutionReaderWrapper; res = MeshSolutionReaderWrapper",
    ".solb Muscat MeshSolutionReaderWrapper": "from Muscat.IO.MeshReader import  MeshSolutionReaderWrapper; res = MeshSolutionReaderWrapper",
    ".stl Muscat StlReader": "from Muscat.IO.StlReader import StlReader; res = StlReader",
    ".stl MeshIO stl_stl_Reader": """from Muscat.Bridges.MeshIOBridge import InitAllReaders, readers; InitAllReaders(); res = readers["MeshIO_stl_stl_Reader"][1]""",
    ".su2 MeshIO su2_su2_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_su2_su2_Reader; res = MeshIO_su2_su2_Reader",
    ".svg MeshIO svg_svg_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_svg_svg_Reader; res = MeshIO_svg_svg_Reader",
    ".tec MeshIO tec_tecplot_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_tec_tecplot_Reader; res = MeshIO_tec_tecplot_Reader",
    ".ugrid MeshIO ugrid_ugrid_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_ugrid_ugrid_Reader; res = MeshIO_ugrid_ugrid_Reader",
    ".ut Muscat UtReader": "from Muscat.IO.UtReader import UtReader; res = UtReader",
    ".utp Muscat UtReader": "from Muscat.IO.UtReader import UtReader; res = UtReader",
    ".vol MeshIO vol_netgen_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_vol_netgen_Reader; res = MeshIO_vol_netgen_Reader",
    ".vol.gz MeshIO vol.gz_netgen_Reader": """from Muscat.Bridges.MeshIOBridge import readers; res = readers['MeshIO_vol.gz_netgen_Reader']""",
    ".vtk MeshIO vtk_vtk_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_vtk_vtk_Reader; res = MeshIO_vtk_vtk_Reader",
    ".vtu MeshIO vtu_vtu_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_vtu_vtu_Reader; res = MeshIO_vtu_vtu_Reader",
    ".wkt MeshIO wkt_wkt_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_wkt_wkt_Reader; res = MeshIO_wkt_wkt_Reader",
    ".xdmf MeshIO xdmf_xdmf_Reader": "from Muscat.Bridges.MeshIOBridge import readers; res = readers['MeshIO_xdmf_xdmf_Reader']",
    ".xdmf Muscat XdmfReader": "from Muscat.IO.XdmfReader import XdmfReader; res = XdmfReader",
    ".xmf Muscat XdmfReader": "from Muscat.IO.XdmfReader import XdmfReader; res = XdmfReader",
    ".xmf MeshIO xmf_xdmf_Reader": "from Muscat.Bridges.MeshIOBridge import MeshIO_xmf_xdmf_Reader; res = MeshIO_xmf_xdmf_Reader",
    ".xml MeshIO xml_dolfin-xml_Reader": """from Muscat.Bridges.MeshIOBridge import readers; res = readers['MeshIO_xml_dolfin-xml_Reader']""",
}
ReaderMapping = DelayInitialization(ReaderDelayedInitStruct)


WriterDelayedInitStruct = {
    ".avs MeshIO avs_avsucd_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_avs_avsucd_Writer"][1]""",
    ".bdf MeshIO bdf_nastran_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_bdf_nastran_Writer"][1]""",
    ".off MeshIO off_off_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_off_off_Writer"][1]""",
    ".cgns MeshIO cgns_cgns_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_cgns_cgns_Writer"][1]""",
    ".nas MeshIO nas_nastran_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_nas_nastran_Writer"][1]""",
    ".mesh Muscat MeshWriter": "from Muscat.IO.MeshWriter import MeshWriter; res = MeshWriter",
    ".dill Muscat DillWriter": "from Muscat.IO.DillTools import DillWriter; res = DillWriter",
    ".stl Muscat StlWriter": "from Muscat.IO.StlWriter import StlWriter; res = StlWriter",
    ".xmf MeshIO xmf_xdmf_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_xmf_xdmf_Writer"][1]""",
    ".med MeshIO med_med_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_med_med_Writer"][1]""",
    ".ply MeshIO ply_ply_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_ply_ply_Writer"][1]""",
    ".tec MeshIO tec_tecplot_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_tec_tecplot_Writer"][1]""",
    ".msh MeshIO msh_gmsh_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_msh_gmsh_Writer"][1]""",
    ".xdmf MeshIO xdmf_xdmf_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_xdmf_xdmf_Writer"][1]""",
    ".cgns Muscat CGNSWriter": "from Muscat.IO.CGNSWriter import CGNSWriter; res = CGNSWriter",
    ".vtk MeshIO vtk_vtk_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_vtk_vtk_Writer"][1]""",
    ".h5m MeshIO h5m_h5m_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_h5m_h5m_Writer"][1]""",
    ".su2 MeshIO su2_su2_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_su2_su2_Writer"][1]""",
    ".vol.gz MeshIO vol.gz_netgen_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_vol.gz_netgen_Writer"][1]""",
    ".ele MeshIO ele_tetgen_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_ele_tetgen_Writer"][1]""",
    ".msh Muscat GmshWriter": "from Muscat.IO.GmshWriter import GmshWriter; res = GmshWriter",
    ".ugrid MeshIO ugrid_ugrid_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_ugrid_ugrid_Writer"][1]""",
    ".node MeshIO node_tetgen_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_node_tetgen_Writer"][1]""",
    ".wkt MeshIO wkt_wkt_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_wkt_wkt_Writer"][1]""",
    ".inp Muscat InpWriter": "from Muscat.IO.InpWriter import InpWriter; res = InpWriter",
    ".dat MeshIO dat_tecplot_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_dat_tecplot_Writer"][1]""",
    ".f3grid MeshIO f3grid_flac3d_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_f3grid_flac3d_Writer"][1]""",
    ".dato.gz MeshIO dato.gz_permas_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_dato.gz_permas_Writer"][1]""",
    ".vtu MeshIO vtu_vtu_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_vtu_vtu_Writer"][1]""",
    ".hmf MeshIO hmf_hmf_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_hmf_hmf_Writer"][1]""",
    ".mesh MeshIO mesh_medit_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_mesh_medit_Writer"][1]""",
    ".xmf Muscat XdmfWriter": "from Muscat.IO.XdmfWriter import XdmfWriter; res = XdmfWriter",
    ".fem MeshIO fem_nastran_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_fem_nastran_Writer"][1]""",
    ".stl MeshIO stl_stl_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_stl_stl_Writer"][1]""",
    ".xdmf Muscat XdmfWriter": "from Muscat.IO.XdmfWriter import XdmfWriter; res = XdmfWriter",
    ".obj MeshIO obj_obj_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_obj_obj_Writer"][1]""",
    ".pickle Muscat PickleWriter": "from Muscat.IO.PickleTools import PickleWriter; res = PickleWriter",
    ".svg MeshIO svg_svg_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_svg_svg_Writer"][1]""",
    ".msh MeshIO msh_ansys_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_msh_ansys_Writer"][1]""",
    ".inp MeshIO inp_abaqus_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_inp_abaqus_Writer"][1]""",
    ".meshb Muscat MeshWriter": "from Muscat.IO.MeshWriter import MeshWriter; res = MeshWriter",
    ".dato MeshIO dato_permas_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_dato_permas_Writer"][1]""",
    ".xml MeshIO xml_dolfin-xml_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_xml_dolfin-xml_Writer"][1]""",
    ".geof Muscat GeofWriter": "from Muscat.IO.GeofWriter import GeofWriter; res = GeofWriter",
    ".post MeshIO post_permas_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_post_permas_Writer"][1]""",
    ".meshb MeshIO meshb_medit_Writer": """from Muscat.Bridges.MeshIOBridge import InitAllWriters, writers; InitAllWriters(); res = writers["MeshIO_meshb_medit_Writer"][1]""",
    ".csv Muscat CsvWriter": "from Muscat.IO.CsvWriter import CsvWriter; res = CsvWriter",
    ".vol MeshIO vol_netgen_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_vol_netgen_Writer"][1]""",
    ".mdpa MeshIO mdpa_mdpa_Writer": """from Muscat.Bridges.MeshIOBridge import writers; res = writers["MeshIO_mdpa_mdpa_Writer"][1]""",
}

WriterMapping = DelayInitialization(WriterDelayedInitStruct)

try:
    from Muscat.Bridges.MeshIOBridge import InitAllReaders, InitAllWriters

    InitAllWriters()
    InitAllReaders()
except ImportError:
    pass


def mesh_file_conversion(
    inputs: Mapping[str, Any], parameters: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Convert a mesh while preserving the explicit reader/writer algorithm.

    Parameters
    ----------
    inputs : collections.abc.Mapping[str, Any]
        Input and output filenames.
    parameters : collections.abc.Mapping[str, Any]
        Reader, writer, temporal selection, and binary-output settings.

    Returns
    -------
    collections.abc.Mapping[str, Any]
        The output filename, allowing the node to be chained in a workflow.

    Raises
    ------
    MeshFileConversionError
        If a path, selector, or reader/writer operation is invalid.
    """
    try:
        inputfilename = Path(parameters["input_filename"]).expanduser()
        outputfilename = Path(parameters["output_filename"]).expanduser()
    except (KeyError, TypeError, ValueError) as error:
        raise MeshFileConversionError(
            "input_filename and output_filename must be valid paths"
        ) from error

    if not inputfilename.is_file():
        raise MeshFileConversionError(f"Input mesh file does not exist: {inputfilename}")

    if not outputfilename.parent.is_dir():
        raise MeshFileConversionError(f"Output directory does not exist: {outputfilename.parent}")

    readername = parameters.get("reader", "auto")
    writername = parameters.get("writer", "auto")

    if not inputfilename.suffix and not readername == "auto":
        raise MeshFileConversionError("Input mesh filenames must have extensions")
    if not outputfilename.suffix and not writername == "auto":
        raise MeshFileConversionError("Output mesh filenames must have extensions")

    binary = parameters.get("binary", True)

    try:
        reader = ReaderMapping.GetClass(inputfilename, readername)()
        writer = WriterMapping.GetClass(outputfilename, writername)()
    except (KeyError, MeshFileConversionError) as error:
        raise MeshFileConversionError(f"Could not select reader or writer: {error}") from error

    reader.SetFileName(inputfilename)
    timestep_to_read = parameters.get("timestep_to_read", "last")

    def DoWrite(the_mesh, the_writer, **extras):
        PointFieldsNames = list(the_mesh.nodeFields.keys())
        PointFields = list(the_mesh.nodeFields.values())
        CellFieldsNames = list(the_mesh.elemFields.keys())
        CellFields = list(the_mesh.elemFields.values())
        the_writer.Write(
            the_mesh,
            PointFieldsNames=PointFieldsNames,
            PointFields=PointFields,
            CellFieldsNames=CellFieldsNames,
            CellFields=CellFields,
            **extras,
        )

    if reader.canHandleTemporal:
        reader.ReadMetaData()
        timesAvailable = reader.GetAvailableTimes()
        writer.SetFileName(outputfilename)
        if hasattr(writer, "SetBinary"):
            writer.SetBinary(binary)

        if timestep_to_read == "first":
            times = [0]
        elif timestep_to_read == "last":
            times = [timesAvailable[-1]]
        elif timestep_to_read == "all":
            times = timesAvailable
        else:
            from Muscat.Helpers.ParserHelper import ReadInts

            times = timesAvailable[ReadInts(timestep_to_read)]

        if writer.canHandleTemporal:
            writer.SetTemporal()
            writer.Open(outputfilename)
            try:
                for t in times:
                    reader.SetTimeToRead(t)
                    mesh = reader.Read()
                    DoWrite(mesh, writer, Time=t)
            finally:
                writer.Close()
        else:
            writer.Open(outputfilename)
            try:
                DoWrite(reader.Read(), writer)
            finally:
                writer.Close()

    else:
        mesh = reader.Read()
        writer.SetFileName(outputfilename)
        if hasattr(writer, "SetBinary"):
            writer.SetBinary(binary)
        writer.Open()
        try:
            DoWrite(mesh, writer)
        finally:
            writer.Close()

    return {"converted_filename": str(outputfilename)}


MESH_FILE_CONVERSION = NodeDefinition(
    id="convert-mesh-file-format",
    icon="mdi--file-swap",
    label="Convert Mesh File Format",
    description="Read and write a mesh (and solutions if supported) to a new format file",
    ports=(PortDefinition("converted_filename", PortDirection.OUTPUT, FILE, "Output Filename"),),
    executor=mesh_file_conversion,
    parameters=(
        ParameterDefinition("input_filename", ParameterKind.FILE, "Input Filename", ""),
        ParameterDefinition("output_filename", ParameterKind.FILE, "Output Filename", ""),
        ParameterDefinition(
            "reader",
            ParameterKind.STR_SELECT,
            "Reader",
            "auto",
            options=(ParameterOption("auto", "Auto"),)
            + tuple(ParameterOption(k, k) for k in ReaderMapping.keys()),  # noqa: SIM118
            port=False,
        ),
        ParameterDefinition(
            "writer",
            ParameterKind.STR_SELECT,
            "Writer",
            "auto",
            options=(ParameterOption("auto", "Auto"),)
            + tuple(ParameterOption(k, k) for k in WriterMapping.keys()),  # noqa: SIM118
            port=False,
        ),
        ParameterDefinition(
            "timestep_to_read",
            ParameterKind.STR_SELECT,
            "Timestep to read",
            "last",
            options=(
                ParameterOption("first", "First time step"),
                ParameterOption("last", "Last time step"),
                ParameterOption("all", "All time steps"),
                # ParameterOption("Selected time step", "selected")
            ),
            port=False,
        ),
        ParameterDefinition(
            "binary", ParameterKind.BOOLEAN, "binary (if available)", True, port=False
        ),
        # ParameterDefinition(
        #    "timestep", ParameterKind.LIST_INT, "time step to read", [-1], port=True
        # ),
    ),
)

__all__ = [
    "MESH_FILE_CONVERSION",
]
