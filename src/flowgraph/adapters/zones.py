"""Muscat implicit geometry objects and operators for spatial mesh selection."""

from collections.abc import Mapping
from typing import Any

import numpy as np
from Muscat.ImplicitGeometry import ImplicitGeometryObjects as objects
from Muscat.ImplicitGeometry import ImplicitGeometryOperators as operators

from flowgraph.adapters.data_types import (
    ARRAY_1D,
    BOOLEAN,
    FILE,
    FLOAT,
    INTEGER,
    LIST_FLOAT,
    LIST_STR,
    MESH_DOCUMENT,
    MUSCAT_ZONE,
    STRING,
    VEC3D,
    VEC3DI,
)
from flowgraph.application.workflow_core import (
    ExecContext,
    NodeDefinition,
    ParameterDefinition,
    ParameterOption,
    PortDefinition,
    PortDirection,
)


def _parameter(name, kind, default, choices=()):
    return ParameterDefinition(
        name,
        kind,
        name,
        default,
        options=tuple(ParameterOption(value, str(value)) for value in choices),
        port=kind is not BOOLEAN,
    )


def _input(name, kind, required=True, expandable=0):
    return PortDefinition(
        name, PortDirection.INPUT, kind, name, required=required, expandable=expandable
    )


def _definition(name, label, parameters=(), ports=(), *, operator=False):
    """Build a node with explicit metadata and a fresh geometry per execution."""
    module = operators if operator else objects
    geometry_class = getattr(module, f"ImplicitGeometry{name}")

    def execute(
        inputs: Mapping[str, Any],
        parameters: Mapping[str, Any],
        _exec_context: ExecContext | None = None,
    ) -> Mapping[str, Any]:
        values = {parameter.name: parameter.default for parameter in definition.parameters}
        values.update(parameters)
        values.update({key: value for key, value in inputs.items() if key in values})
        for parameter in definition.parameters:
            if parameter.options and values[parameter.name] not in tuple(
                option.value for option in parameter.options
            ):
                raise ValueError(f"Unsupported {parameter.name}: {values[parameter.name]!r}")
            if parameter.kind in (FLOAT, INTEGER) and not np.isfinite(values[parameter.name]):
                raise ValueError(f"{parameter.name} must be finite")
            if parameter.kind in (VEC3D, VEC3DI):
                value = np.asarray(values[parameter.name], dtype=float)
                if value.shape != (3,) or not np.all(np.isfinite(value)):
                    raise ValueError(f"{parameter.name} must contain three finite components")
                if parameter.kind is VEC3DI and np.any(value != np.floor(value)):
                    raise ValueError(f"{parameter.name} must contain integers")
                values[parameter.name] = value.copy()
        for key in ("radius", "size", "scale", "lx", "n", "r", "numberOfElementPseudoDistance"):
            if key in values and (
                not np.all(np.isfinite(values[key])) or np.any(np.asarray(values[key]) <= 0)
            ):
                raise ValueError(f"{key} must be positive and finite")
        for key in ("thickness", "w", "wallThickness", "smoothControl"):
            if key in values and values[key] < 0:
                raise ValueError(f"{key} must be nonnegative")
        if name == "Plane" and not np.linalg.norm(values["normal"]):
            raise ValueError("normal must be nonzero")
        if name == "Cylinder" and np.array_equal(values["center1"], values["center2"]):
            raise ValueError("Cylinder axis endpoints must be distinct")

        if name == "Transform":
            if not np.linalg.norm(values["first"]) or not np.linalg.norm(
                np.cross(values["first"], values["second"])
            ):
                raise ValueError("Transform axes must be nonzero and nonparallel")
            zone = geometry_class(
                inputs["zone"], values["offset"], values["first"], values["second"]
            )
        elif name == "Ellipse":
            # Muscat's inherited SetRadius uses ReadFloat, which rejects a vector.
            zone = geometry_class(radius=1.0, center=values["center"])
            zone.radius = values["radius"]
        else:
            zone = geometry_class()
            for key, value in values.items():
                if name != "ExternalSurface" or key != "method":
                    setattr(zone, key, value)
            if name == "Plane":
                zone.SetNormal(values["normal"])
            elif name == "Wrapped":
                field = np.asarray(values["field"])
                if field.ndim == 2 and field.shape[1] == 1:
                    field = field[:, 0]
                if field.ndim != 1 or not field.size:
                    raise ValueError(
                        f"Wrapped Field requires nonempty scalar data of shape (n,) or (n, 1); "
                        f"received shape {field.shape}"
                    )
                if field.dtype.kind not in "iuf":
                    raise TypeError("Wrapped Field requires real integer or floating-point values")
                if not np.all(np.isfinite(field)):
                    raise ValueError("Wrapped Field requires finite signed distances")
                zone.field = field.view()
                zone.field.setflags(write=False)
            elif name == "ExternalSurface":
                if values["method"] not in ("bulk", "normal"):
                    raise ValueError("method must be bulk or normal")
                zone._method = values["method"]
                zone.SetSupport(inputs["mesh"].mesh)
            elif name in ("ByETag", "ByETagII"):
                if name == "ByETagII":
                    zone.SetSupportAndZones(inputs["mesh"].mesh, values["etags"], dim=[])
                else:
                    zone.SetSupportAndZones(inputs["mesh"].mesh, values["etags"])
            elif name == "SphereFromNTag":
                zone.SetSupport(inputs["mesh"].mesh)
                if not len(zone.centers):
                    raise ValueError("nTag must select at least one node")
            elif name == "Stl":
                zone.LoadFromFile(str(values["filename"]))
            elif name == "Holes":
                zone.SetSupport(inputs["mesh"].mesh)
            elif name in ("Union", "Intersection"):
                zone.Zones = [value for key, value in inputs.items() if key.startswith("zone_")]
                if not zone.Zones:
                    raise ValueError(f"{label} requires at least one zone")
            elif name == "Difference":
                zone.Zone1, zone.Zone2 = inputs["zone1"], inputs["zone2"]
            elif operator:
                zone.Zone1 = inputs["zone"]
        return {"zone": zone}

    definition = NodeDefinition(
        id=f"zone-{name.lower()}",
        label=label,
        icon="mdi-shape-outline",
        description=f"Creates a Muscat {geometry_class.__name__} zone.",
        requirements=("py:muscat", "py:sympy") if name == "Analytical" else ("py:muscat",),
        ports=(*ports, PortDefinition("zone", PortDirection.OUTPUT, MUSCAT_ZONE, "Zone")),
        parameters=tuple(parameters),
        executor=execute,
    )
    return definition


_CENTER = _parameter("center", VEC3D, [0.0, 0.0, 0.0])
_RADIUS = _parameter("radius", FLOAT, 1.0)
_OFFSET = _parameter("offset", FLOAT, 0.0)
_VECTOR_OFFSET = _parameter("offset", VEC3D, [0.0, 0.0, 0.0])
_SMOOTH = _parameter("smoothControl", FLOAT, 0.0)
_LATTICE = (_parameter("lx", FLOAT, 1.0), _parameter("w", FLOAT, 0.1))
_MESH = _input("mesh", MESH_DOCUMENT)
_ZONE = _input("zone", MUSCAT_ZONE)

AVAILABLE_NODES = (
    _definition(
        "Wrapped",
        "Wrapped Field",
        (ParameterDefinition("field", LIST_FLOAT, "field", [0.0], port=False),),
        (_input("field", ARRAY_1D, required=False),),
    ),
    _definition(
        "ExternalSurface",
        "External Surface",
        (
            _parameter("method", STRING, "bulk", ("bulk", "normal")),
            _parameter("offset", FLOAT, 0.001),
        ),
        (_MESH,),
    ),
    _definition(
        "ByETag",
        "By Element Tag",
        (
            _parameter("etags", LIST_STR, []),
            _OFFSET,
        ),
        (_MESH,),
    ),
    _definition(
        "ByETagII",
        "By Element Tag II",
        (
            _parameter("etags", LIST_STR, []),
            _OFFSET,
            _parameter("numberOfElementPseudoDistance", INTEGER, 10),
        ),
        (_MESH,),
    ),
    _definition(
        "AxisAlignBox",
        "Axis-Aligned Box",
        (
            _parameter("origin", VEC3D, [0.0, 0.0, 0.0]),
            _parameter("size", VEC3D, [1.0, 1.0, 1.0]),
        ),
    ),
    _definition(
        "SphereFromNTag",
        "Spheres From Node Tag",
        (
            _RADIUS,
            _parameter("nTag", STRING, ""),
        ),
        (_MESH,),
    ),
    _definition("Sphere", "Sphere", (_RADIUS, _CENTER)),
    _definition("Ellipse", "Ellipse", (_parameter("radius", VEC3D, [1.0, 1.0, 1.0]), _CENTER)),
    _definition(
        "Cylinder",
        "Cylinder",
        (
            _parameter("center1", VEC3D, [0.0, 0.0, 0.0]),
            _parameter("center2", VEC3D, [1.0, 0.0, 0.0]),
            _RADIUS,
            _parameter("wcups", BOOLEAN, True),
        ),
    ),
    _definition(
        "Plane",
        "Plane",
        (
            _parameter("point", VEC3D, [0.0, 0.0, 0.0]),
            _parameter("normal", VEC3D, [1.0, 0.0, 0.0]),
            _OFFSET,
        ),
    ),
    _definition(
        "Gyroid",
        "Gyroid",
        (
            _parameter("scale", FLOAT, 1.0),
            _VECTOR_OFFSET,
            _parameter("type", INTEGER, 0, (0, 1, 2)),
            _parameter("wall", BOOLEAN, False),
            _parameter("wallThickness", FLOAT, 0.5),
        ),
    ),
    _definition("60D", "60 Degree Walls", _LATTICE),
    _definition(
        "Honeycomb", "Honeycomb", (*_LATTICE, _parameter("translate", VEC3D, [0.0, 0.0, 0.0]))
    ),
    _definition("Stl", "STL Surface", (_parameter("filename", FILE, ""),)),
    _definition("Analytical", "Analytical", (_parameter("expression", STRING, "x"),)),
    _definition(
        "Holes",
        "Holes",
        (
            _parameter("r", FLOAT, 0.5),
            _parameter("n", VEC3DI, [3, 3, 3]),
            _VECTOR_OFFSET,
            _parameter("type", STRING, "Aligned", ("Aligned", "Original", "Staggered")),
        ),
        (_MESH,),
    ),
    *(
        _definition(
            name,
            name,
            (_SMOOTH,),
            (_input("zone", MUSCAT_ZONE, required=False, expandable=128),),
            operator=True,
        )
        for name in ("Union", "Intersection")
    ),
    _definition(
        "Difference",
        "Difference",
        (_SMOOTH,),
        (
            _input("zone1", MUSCAT_ZONE),
            _input("zone2", MUSCAT_ZONE),
        ),
        operator=True,
    ),
    _definition("Offset", "Offset", (_OFFSET,), (_ZONE,), operator=True),
    _definition("InsideOut", "Inside Out", (), (_ZONE,), operator=True),
    _definition("Symmetric", "Symmetric", (_CENTER,), (_ZONE,), operator=True),
    _definition("Shell", "Shell", (_parameter("thickness", FLOAT, 0.1),), (_ZONE,), operator=True),
    _definition(
        "Transform",
        "Transform",
        (
            _VECTOR_OFFSET,
            _parameter("first", VEC3D, [1.0, 0.0, 0.0]),
            _parameter("second", VEC3D, [0.0, 1.0, 0.0]),
        ),
        (_ZONE,),
        operator=True,
    ),
)
