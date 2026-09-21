"""Browser-safe FlowGraph node registry for the Pyodide/Muscat runtime."""

from __future__ import annotations

from flowgraph.adapters.controls import AVAILABLE_NODES as CONTROL_NODES
from flowgraph.adapters.documentation import AVAILABLE_NODES as DOCUMENTATION_NODES
from flowgraph.adapters.files import SELECT_FILE, SELECT_SERVER_FILE
from flowgraph.adapters.filters import CREATE_MUSCAT_ELEMENT_FILTER, FILTER_MESH_WITH_MUSCAT
from flowgraph.adapters.image_tools import AVAILABLE_NODES as IMAGE_TOOL_NODES
from flowgraph.adapters.mesh_creation_tools import AVAILABLE_NODES as MESH_CREATION_NODES
from flowgraph.adapters.mesh_ops import AVAILABLE_NODES as MESH_OPERATION_NODES
from flowgraph.adapters.file_conversion import MESH_FILE_CONVERSION
from flowgraph.adapters.remote_files import AVAILABLE_NODES as REMOTE_FILE_NODES
from flowgraph.adapters.simple_sources import AVAILABLE_NODES as SIMPLE_SOURCE_NODES
from flowgraph.adapters.sinks import DISPLAY_VALUE, SHOW_IMAGE
from flowgraph.adapters.user_code import AVAILABLE_NODES as USER_CODE_NODES
from flowgraph.adapters.workflow import AVAILABLE_NODES as WORKFLOW_NODES
from flowgraph.adapters.workflow_interfaces import AVAILABLE_NODES as WORKFLOW_INTERFACE_NODES
from flowgraph.application.workflow_core import NodeRegistry

WASM_NODE_DEFINITIONS = (
    *SIMPLE_SOURCE_NODES,
    SELECT_FILE,
    SELECT_SERVER_FILE,
    *REMOTE_FILE_NODES,
    *IMAGE_TOOL_NODES,
    *CONTROL_NODES,
    *MESH_CREATION_NODES,
    MESH_FILE_CONVERSION,
    CREATE_MUSCAT_ELEMENT_FILTER,
    FILTER_MESH_WITH_MUSCAT,
    *MESH_OPERATION_NODES,
    *USER_CODE_NODES,
    *WORKFLOW_INTERFACE_NODES,
    *WORKFLOW_NODES,
    SHOW_IMAGE,
    DISPLAY_VALUE,
    *DOCUMENTATION_NODES,
)


def create_wasm_node_registry() -> NodeRegistry:
    """Return nodes supported by the initial VTK-free browser runtime.

    The registry deliberately excludes local-file readers/writers, desktop view
    sinks, Trame integrations, external tools, and adapters whose dependencies
    are not staged in the initial Pyodide/Muscat distribution.
    """
    registry = NodeRegistry()
    for definition in WASM_NODE_DEFINITIONS:
        registry.register(definition)
    return registry


__all__ = ["WASM_NODE_DEFINITIONS", "create_wasm_node_registry"]
