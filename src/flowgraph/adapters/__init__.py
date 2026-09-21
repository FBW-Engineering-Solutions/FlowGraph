"""Grouped catalog of workflow adapters exposed to application composition."""

from dataclasses import dataclass

from flowgraph.adapters.controls import AVAILABLE_NODES as CONTROL_AVAILABLE_NODES
from flowgraph.adapters.cosapp import AVAILABLE_NODES as COSAPP_AVAILABLE_NODES
from flowgraph.adapters.documentation import AVAILABLE_NODES as DOCUMENTATION_AVAILABLE_NODES
from flowgraph.adapters.field_ops import AVAILABLE_NODES as FIELD_OPS_AVAILABLE_NODES
from flowgraph.adapters.file_conversion import MESH_FILE_CONVERSION
from flowgraph.adapters.files import (
    READ_DIRECTORY_FILES,
    SELECT_FILE,
    SELECT_SERVER_FILE,
)
from flowgraph.adapters.filters import (
    CREATE_MUSCAT_ELEMENT_FILTER,
    FILTER_MESH_WITH_MUSCAT,
)
from flowgraph.adapters.image_tools import AVAILABLE_NODES as IMAGE_TOOLS_AVAILABLE_NODES
from flowgraph.adapters.mesh_creation_tools import AVAILABLE_NODES as MESH_CREATION_AVAILABLE_NODES
from flowgraph.adapters.mesh_generations import CSV_TO_MESH
from flowgraph.adapters.mesh_ops import AVAILABLE_NODES as MESH_OPS_AVAILABLE_NODES
from flowgraph.adapters.plaid_bridge import AVAILABLE_NODES as PLAID_AVAILABLE_NODES
from flowgraph.adapters.readers import (
    LOAD_CSV,
    LOAD_MESHIO,
    LOAD_MESHLANE,
    LOAD_MUSCAT,
)
from flowgraph.adapters.remote_files import DOWNLOAD_URL
from flowgraph.adapters.simple_sources import (
    SET_FLOAT,
    SET_INT,
    SET_LIST_FLOAT,
    SET_LIST_INT,
    SET_LIST_STR,
    SET_STRING,
    SET_VEC3D,
)
from flowgraph.adapters.sinks import AVAILABLE_NODES as SINKS_AVAILABLE_NODES
from flowgraph.adapters.user_code import AVAILABLE_NODES as USER_CODE_AVAILABLE_NODES
from flowgraph.adapters.workflow import AVAILABLE_NODES as WORKFLOW_AVAILABLE_NODES
from flowgraph.adapters.workflow_interfaces import (
    AVAILABLE_NODES as WORKFLOW_INTERFACE_AVAILABLE_NODES,
)
from flowgraph.adapters.writers import WRITE_MESHIO, WRITE_MESHLANE, WRITE_MUSCAT
from flowgraph.application.workflow_core import NodeDefinition


@dataclass(frozen=True)
class AdapterGroup:
    """A named, ordered group of workflow nodes presented in one UI menu."""

    label: str
    node_definitions: tuple[NodeDefinition, ...] = ()
    subgroups: tuple["AdapterGroup", ...] = ()

    def all_node_definitions(self) -> tuple[NodeDefinition, ...]:
        """Return definitions in this group and all nested groups."""
        return self.node_definitions + tuple(
            definition
            for subgroup in self.subgroups
            for definition in subgroup.all_node_definitions()
        )


@dataclass(frozen=True)
class AdapterCatalog:
    """Single application-facing catalog for adapter nodes and their UI metadata."""

    groups: tuple[AdapterGroup, ...]

    @property
    def node_definitions(self) -> tuple[NodeDefinition, ...]:
        """Return all adapter definitions in group and menu order."""
        return tuple(
            definition for group in self.groups for definition in group.all_node_definitions()
        )

    def require(self, definition_id: str) -> NodeDefinition:
        """Return an adapter definition by ID or raise a descriptive key error."""
        definition = next(
            (candidate for candidate in self.node_definitions if candidate.id == definition_id),
            None,
        )
        if definition is None:
            raise KeyError(f"Unknown adapter node definition: {definition_id!r}")
        return definition


ADAPTERS = AdapterCatalog(
    groups=(
        AdapterGroup(
            "Inputs",
            subgroups=(
                AdapterGroup("Scalars", (SET_STRING, SET_INT, SET_FLOAT)),
                AdapterGroup(
                    "Lists/Vectors", (SET_LIST_STR, SET_LIST_INT, SET_LIST_FLOAT, SET_VEC3D)
                ),
                AdapterGroup(
                    "Files",
                    (SELECT_FILE, SELECT_SERVER_FILE, DOWNLOAD_URL, READ_DIRECTORY_FILES),
                ),
            ),
        ),
        AdapterGroup(
            "Mesh Tools",
            subgroups=(
                AdapterGroup(
                    "Readers",
                    (LOAD_MUSCAT, LOAD_MESHIO, LOAD_MESHLANE, LOAD_CSV),
                ),
                AdapterGroup("Mesh Gens", (CSV_TO_MESH,)),
                AdapterGroup("Mesh Creation", MESH_CREATION_AVAILABLE_NODES),
                AdapterGroup(
                    "Filters",
                    (CREATE_MUSCAT_ELEMENT_FILTER, FILTER_MESH_WITH_MUSCAT),
                ),
                AdapterGroup("Mesh Ops", MESH_OPS_AVAILABLE_NODES),
                AdapterGroup("Field Ops", FIELD_OPS_AVAILABLE_NODES),
                AdapterGroup("File Conversion", (MESH_FILE_CONVERSION,)),
                AdapterGroup("Writers", (WRITE_MUSCAT, WRITE_MESHLANE, WRITE_MESHIO)),
            ),
        ),
        AdapterGroup("Controls", CONTROL_AVAILABLE_NODES),
        AdapterGroup("Image Tools", IMAGE_TOOLS_AVAILABLE_NODES),
        AdapterGroup("Code", USER_CODE_AVAILABLE_NODES),
        AdapterGroup("Workflow", WORKFLOW_INTERFACE_AVAILABLE_NODES + WORKFLOW_AVAILABLE_NODES),
        AdapterGroup("Sinks", SINKS_AVAILABLE_NODES),
        AdapterGroup("Doc", DOCUMENTATION_AVAILABLE_NODES),
        AdapterGroup(
            "External Tools",
            subgroups=(
                AdapterGroup("CoSApp", COSAPP_AVAILABLE_NODES),
                AdapterGroup("Plaid", PLAID_AVAILABLE_NODES),
            ),
        ),
    ),
)

__all__ = ["ADAPTERS"]
