from Muscat.LinAlg.Transform import Transform
from Muscat.MeshContainers.Filters.FilterObjects import ElementFilter
from Muscat.MeshContainers.Filters.FilterOperators import FilterOperatorBase
from PIL.Image import Image

from flowgraph.application.workflow_core import DataType
from flowgraph.domain.mesh_document import MeshDocument

ANY = DataType("any", "Any", object)
STRING = DataType("string", "Text", str)
STR_SELECT = DataType("str", "select str", str)
BOOLEAN = DataType("boolean", "Boolean", bool)
INTEGER = DataType("integer", "Integer", int)
FLOAT = DataType("float", "Float", float)
LIST_STR = DataType("list[str]", "List Text", list[str])
LIST_INT = DataType("list[int]", "List Ints", list[int])
LIST_FLOAT = DataType("list[float]", "List Floats", list[float])
LIST_ANY = DataType("list[any]", "List Any", list)
FILE = DataType("filename", "Path", str)

MESH_DOCUMENT = DataType("mesh-document", "Mesh document", MeshDocument)
TABLE_DOCUMENT = DataType("table-document", "Table", dict)
IMAGE = DataType("image", "Image", Image)
MUSCAT_ELEMENT_FILTER = DataType(
    "filter-like",
    "Selector",
    (ElementFilter, FilterOperatorBase),
)
VEC3D = DataType("VEC3D", "3D Vector", list[float])
VEC2D = DataType("VEC2D", "2D Vector", list[float])
VEC3DSTR = DataType("VEC3DSTR", "3D Text Vector", list[str])

VEC3DI = DataType("VEC3D", "3D Vector", list[int])
VEC2DI = DataType("VEC2D", "2D Vector", list[int])


MULTI_SELECT = DataType("list[bool]", "List bool", list[bool])
SELECT_SERVER_FILENAME = DataType("ServerFile", "Text", str)

TRANSFORM_T = DataType("Transform", "Transform", Transform)


class ParameterKind:
    """UI-neutral editor semantics for a persisted node parameter."""

    TEXT = STRING
    STR_SELECT = STR_SELECT
    BOOLEAN = BOOLEAN
    INTEGER = INTEGER
    FLOAT = FLOAT
    LIST_STR = LIST_STR
    LIST_INT = LIST_INT
    LIST_FLOAT = LIST_FLOAT
    FILE = FILE
    VEC3D = VEC3D
    VEC2D = VEC2D
    VEC3DSTR = VEC3DSTR
    MULTI_SELECT = MULTI_SELECT
    SELECT_SERVER_FILENAME = SELECT_SERVER_FILENAME
