"""Workflow nodes for Muscat mesh creation and conversion tools."""

from collections.abc import Mapping
from math import pi
from typing import Any

from Muscat.MeshContainers import ElementsDescription as ED
from Muscat.MeshContainers.ElementsContainers import ElementsContainer
from Muscat.MeshTools.MeshCreationTools import (
    Create0DElementContainerForEveryPoint,
    CreateCube,
    CreateDisk,
    CreateMeshFromCellsDict,
    CreateMeshOf,
    CreateMeshOfTriangles,
    CreateSquare,
    CreateUniformMeshOfBars,
    MeshToSimplex,
    MirrorMesh,
    QuadToLin,
    SubDivideMesh,
    ToQuadraticMesh,
)

from flowgraph.application.workflow_core import (
    DataType,
    NodeDefinition,
    ParameterDefinition,
    ParameterOption,
    PortDefinition,
    PortDirection,
)
from flowgraph.domain.mesh_document import MeshDocument

from .data_types import ANY, INTEGER, MESH_DOCUMENT, VEC2DI, VEC3DI, ParameterKind

ELEMENTS_CONTAINER = DataType("elements-container", "Elements container", ElementsContainer)

_ELEMENT_OPTIONS = tuple(
    ParameterOption(element.name, element.name)
    for element in ED.ElementType
    if element is not ED.ElementType.Element_NA
)


def _element_type(value: Any) -> ED.ElementType:
    """Convert a persisted element-type name or enum to a Muscat element type."""
    if isinstance(value, ED.ElementType):
        return value
    if isinstance(value, str):
        try:
            return ED.ElementType[value]
        except KeyError as error:
            raise ValueError(f"Unknown Muscat element type: {value!r}") from error
    raise TypeError("elemName must be a Muscat ElementType or its name")


def _mesh_result(mesh) -> Mapping[str, Any]:
    """Wrap a Muscat mesh in the canonical FlowGraph mesh document."""
    return {"mesh": MeshDocument(mesh=mesh)}


def _create_uniform_bars(
    _inputs: Mapping[str, Any], parameters: Mapping[str, Any]
) -> Mapping[str, Any]:
    return _mesh_result(
        CreateUniformMeshOfBars(
            parameters.get("startPoint", 0.0),
            parameters.get("stopPoint", 1.0),
            nbPoints=parameters.get("nbPoints", 50),
            secondOrder=parameters.get("secondOrder", False),
        )
    )


def _create_triangles(
    inputs: Mapping[str, Any], _parameters: Mapping[str, Any]
) -> Mapping[str, Any]:
    return _mesh_result(CreateMeshOfTriangles(inputs["points"], inputs["triangles"]))


def _create_mesh(inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mesh_result(
        CreateMeshOf(
            inputs["points"], inputs["connectivity"], _element_type(parameters["elemName"])
        )
    )


def _create_square(_inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mesh_result(
        CreateSquare(
            dimensions=parameters.get("dimensions", [2, 2]),
            origin=parameters.get("origin", [-1.0, -1.0]),
            spacing=parameters.get("spacing", [1.0, 1.0]),
            ofTriangles=parameters.get("ofTriangles", False),
        )
    )


def _create_disk(_inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mesh_result(
        CreateDisk(
            nr=parameters.get("nr", 10),
            nTheta=parameters.get("nTheta", 10),
            r0=parameters.get("r0", 0.5),
            r1=parameters.get("r1", 1.0),
            theta0=parameters.get("theta0", 0.0),
            theta1=parameters.get("theta1", pi / 2),
            ofTriangles=parameters.get("ofTriangles", False),
        )
    )


def _create_cube(_inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mesh_result(
        CreateCube(
            dimensions=parameters.get("dimensions", [2, 2, 2]),
            origin=parameters.get("origin", [-1.0, -1.0, -1.0]),
            spacing=parameters.get("spacing", [1.0, 1.0, 1.0]),
            ofTetras=parameters.get("ofTetras", False),
        )
    )


def _create_mesh_from_cells_dict(
    inputs: Mapping[str, Any], parameters: Mapping[str, Any]
) -> Mapping[str, Any]:
    return _mesh_result(
        CreateMeshFromCellsDict(
            inputs["points"],
            inputs["cellsDict"],
            pointFields=inputs["pointFields"],
            cellFields=inputs["cellFields"],
            cellFieldInDictOrder=parameters.get("cellFieldInDictOrder", True),
            originalIds=inputs["originalIds"],
            cellsOriginalIds=inputs["cellsOriginalIds"],
        )
    )


def _mesh_to_simplex(inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mesh_result(
        MeshToSimplex(inputs["mesh"].mesh, inPlace=parameters.get("inPlace", False))
    )


def _to_quadratic_mesh(
    inputs: Mapping[str, Any], _parameters: Mapping[str, Any]
) -> Mapping[str, Any]:
    return _mesh_result(ToQuadraticMesh(inputs["inputMesh"].mesh))


def _quad_to_lin_creation(
    inputs: Mapping[str, Any], parameters: Mapping[str, Any]
) -> Mapping[str, Any]:
    return {
        "outputMesh": MeshDocument(
            mesh=QuadToLin(
                inputs["inputMesh"].mesh,
                divideQuadElements=parameters.get("divideQuadElements", True),
                linearizedMiddlePoints=parameters.get("linearizedMiddlePoints", False),
            )
        )
    }


def _mirror_mesh(inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mesh_result(
        MirrorMesh(
            inputs["inmesh"].mesh,
            x=parameters.get("x"),
            y=parameters.get("y"),
            z=parameters.get("z"),
            propagateToNodeFields=parameters.get("propagateToNodeFields", False),
        )
    )


def _create_zero_d_elements(
    inputs: Mapping[str, Any], _parameters: Mapping[str, Any]
) -> Mapping[str, Any]:
    return {"elements": Create0DElementContainerForEveryPoint(inputs["mesh"].mesh)}


def _subdivide_mesh(inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mesh_result(SubDivideMesh(inputs["mesh"].mesh, level=parameters.get("level", 1)))


def _mesh_output(name: str = "mesh") -> tuple[PortDefinition, ...]:
    return (PortDefinition(name, PortDirection.OUTPUT, MESH_DOCUMENT, "Mesh"),)


def _mesh_input_output(input_name: str, output_name: str = "mesh") -> tuple[PortDefinition, ...]:
    return (
        PortDefinition(input_name, PortDirection.INPUT, MESH_DOCUMENT, "Input mesh"),
        PortDefinition(output_name, PortDirection.OUTPUT, MESH_DOCUMENT, "Output mesh"),
    )


CREATE_UNIFORM_MESH_OF_BARS_NODE = NodeDefinition(
    id="create-uniform-mesh-of-bars",
    icon="mdi-vector-line",
    label="Create Uniform Mesh Of Bars",
    description="Create a uniform Muscat mesh of bars.",
    ports=_mesh_output(),
    executor=_create_uniform_bars,
    parameters=(
        ParameterDefinition("startPoint", ParameterKind.VEC3D, "Start point", [0, 0, 0]),
        ParameterDefinition("stopPoint", ParameterKind.VEC3D, "Stop point", [1, 0, 0]),
        ParameterDefinition("nbPoints", INTEGER, "Number of points", 50),
        ParameterDefinition(
            "secondOrder", ParameterKind.BOOLEAN, "Second order", False, port=False
        ),
    ),
)

CREATE_MESH_OF_TRIANGLES_NODE = NodeDefinition(
    id="create-mesh-of-triangles",
    icon="mdi-triangle-outline",
    label="Create Mesh Of Triangles",
    description="Create a Muscat triangular mesh from points and connectivity.",
    ports=(
        PortDefinition("points", PortDirection.INPUT, ANY, "Points"),
        PortDefinition("triangles", PortDirection.INPUT, ANY, "Triangles"),
        *_mesh_output(),
    ),
    executor=_create_triangles,
)

CREATE_MESH_OF_NODE = NodeDefinition(
    id="create-mesh-of",
    icon="mdi-shape-outline",
    label="Create Mesh Of",
    description="Create a homogeneous Muscat mesh from points and connectivity.",
    ports=(
        PortDefinition("points", PortDirection.INPUT, ANY, "Points"),
        PortDefinition("connectivity", PortDirection.INPUT, ANY, "Connectivity"),
        *_mesh_output(),
    ),
    executor=_create_mesh,
    parameters=(
        ParameterDefinition(
            "elemName",
            ParameterKind.STR_SELECT,
            "Element type",
            "Triangle_3",
            options=_ELEMENT_OPTIONS,
        ),
    ),
)

CREATE_SQUARE_NODE = NodeDefinition(
    id="create-square",
    icon="mdi-grid",
    label="Create Square",
    description="Create a structured Muscat square mesh.",
    ports=_mesh_output(),
    executor=_create_square,
    parameters=(
        ParameterDefinition("dimensions", VEC2DI, "Dimensions", [2, 2]),
        ParameterDefinition("origin", ParameterKind.VEC2D, "Origin", [-1.0, -1.0]),
        ParameterDefinition("spacing", ParameterKind.VEC2D, "Spacing", [1.0, 1.0]),
        ParameterDefinition(
            "ofTriangles", ParameterKind.BOOLEAN, "Use triangles", False, port=False
        ),
    ),
)

CREATE_DISK_NODE = NodeDefinition(
    id="create-disk",
    icon="mdi-circle-outline",
    label="Create Disk",
    description="Create a structured Muscat disk-sector mesh.",
    ports=_mesh_output(),
    executor=_create_disk,
    parameters=(
        ParameterDefinition("nr", INTEGER, "Radial points", 10),
        ParameterDefinition("nTheta", INTEGER, "Angular points", 10),
        ParameterDefinition("r0", ParameterKind.FLOAT, "Inner radius", 0.5),
        ParameterDefinition("r1", ParameterKind.FLOAT, "Outer radius", 1.0),
        ParameterDefinition("theta0", ParameterKind.FLOAT, "Start angle", 0.0),
        ParameterDefinition("theta1", ParameterKind.FLOAT, "End angle", pi / 2),
        ParameterDefinition(
            "ofTriangles", ParameterKind.BOOLEAN, "Use triangles", False, port=False
        ),
    ),
)

CREATE_CUBE_NODE = NodeDefinition(
    id="create-cube",
    icon="mdi-cube-outline",
    label="Create Cube",
    description="Create a structured Muscat cube mesh.",
    ports=_mesh_output(),
    executor=_create_cube,
    parameters=(
        ParameterDefinition("dimensions", VEC3DI, "Dimensions", [2, 2, 2]),
        ParameterDefinition("origin", ParameterKind.VEC3D, "Origin", [-1.0, -1.0, -1.0]),
        ParameterDefinition("spacing", ParameterKind.VEC3D, "Spacing", [1.0, 1.0, 1.0]),
        ParameterDefinition("ofTetras", ParameterKind.BOOLEAN, "Use tetrahedra", False, port=False),
    ),
)

CREATE_MESH_FROM_CELLS_DICT_NODE = NodeDefinition(
    id="create-mesh-from-cells-dict",
    icon="mdi-code-braces-box",
    label="Create Mesh From Cells Dict",
    description="Create a Muscat mesh from points and a dictionary of cells.",
    ports=(
        PortDefinition("points", PortDirection.INPUT, ANY, "Points"),
        PortDefinition("cellsDict", PortDirection.INPUT, ANY, "Cells dictionary"),
        PortDefinition("pointFields", PortDirection.INPUT, ANY, "Point fields"),
        PortDefinition("cellFields", PortDirection.INPUT, ANY, "Cell fields"),
        PortDefinition("originalIds", PortDirection.INPUT, ANY, "Original node IDs"),
        PortDefinition("cellsOriginalIds", PortDirection.INPUT, ANY, "Original cell IDs"),
        *_mesh_output(),
    ),
    executor=_create_mesh_from_cells_dict,
    parameters=(
        ParameterDefinition(
            "cellFieldInDictOrder",
            ParameterKind.BOOLEAN,
            "Fields in dictionary order",
            True,
            port=False,
        ),
    ),
)

MESH_TO_SIMPLEX_NODE = NodeDefinition(
    id="mesh-to-simplex",
    icon="mdi-vector-triangle",
    label="Mesh To Simplex",
    description="Convert a Muscat mesh to simplex elements.",
    ports=_mesh_input_output("mesh"),
    executor=_mesh_to_simplex,
)

TO_QUADRATIC_MESH_NODE = NodeDefinition(
    id="to-quadratic-mesh",
    icon="mdi-vector-square-plus",
    label="To Quadratic Mesh",
    description="Convert a linear Muscat mesh to quadratic elements.",
    ports=_mesh_input_output("inputMesh", "outputMesh"),
    executor=_to_quadratic_mesh,
)

QUAD_TO_LIN_CREATION_NODE = NodeDefinition(
    id="quad-to-lin-creation",
    icon="mdi-vector-square-remove",
    label="To Linear Mesh",
    description="Convert a quadratic Muscat mesh to linear elements.",
    ports=_mesh_input_output("inputMesh", "outputMesh"),
    executor=_quad_to_lin_creation,
    parameters=(
        ParameterDefinition(
            "divideQuadElements",
            ParameterKind.BOOLEAN,
            "Divide quadratic elements",
            True,
            port=False,
        ),
        ParameterDefinition(
            "linearizedMiddlePoints",
            ParameterKind.BOOLEAN,
            "Linearize middle points",
            False,
            port=False,
        ),
    ),
)

MIRROR_MESH_NODE = NodeDefinition(
    id="mirror-mesh",
    icon="mdi-mirror-rectangle",
    label="Mirror Mesh",
    description="Create a mirrored copy of a Muscat mesh across selected planes.",
    ports=_mesh_input_output("inmesh"),
    executor=_mirror_mesh,
    parameters=(
        ParameterDefinition("x", ParameterKind.FLOAT, "YZ plane x", None),
        ParameterDefinition("y", ParameterKind.FLOAT, "XZ plane y", None),
        ParameterDefinition("z", ParameterKind.FLOAT, "XY plane z", None),
        ParameterDefinition(
            "propagateToNodeFields",
            ParameterKind.BOOLEAN,
            "Propagate node fields",
            False,
            port=False,
        ),
    ),
)

CREATE_0D_ELEMENTS_NODE = NodeDefinition(
    id="create-0d-elements-for-every-point",
    icon="mdi-vector-point",
    label="Create 0D Elements For Every Point",
    description="Create a Muscat point-element container for every mesh point.",
    ports=(
        PortDefinition("mesh", PortDirection.INPUT, MESH_DOCUMENT, "Mesh"),
        PortDefinition("elements", PortDirection.OUTPUT, ELEMENTS_CONTAINER, "Elements"),
    ),
    executor=_create_zero_d_elements,
)

SUBDIVIDE_MESH_NODE = NodeDefinition(
    id="subdivide-mesh",
    icon="mdi-vector-split",
    label="Subdivide Mesh",
    description="Subdivide a Muscat mesh one or more times.",
    ports=_mesh_input_output("mesh"),
    executor=_subdivide_mesh,
    parameters=(ParameterDefinition("level", INTEGER, "Subdivision level", 1),),
)

AVAILABLE_NODES = (
    CREATE_UNIFORM_MESH_OF_BARS_NODE,
    CREATE_MESH_OF_TRIANGLES_NODE,
    CREATE_MESH_OF_NODE,
    CREATE_SQUARE_NODE,
    CREATE_DISK_NODE,
    CREATE_CUBE_NODE,
    CREATE_MESH_FROM_CELLS_DICT_NODE,
    MESH_TO_SIMPLEX_NODE,
    TO_QUADRATIC_MESH_NODE,
    QUAD_TO_LIN_CREATION_NODE,
    MIRROR_MESH_NODE,
    CREATE_0D_ELEMENTS_NODE,
    SUBDIVIDE_MESH_NODE,
)
