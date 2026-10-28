---
id: reference.adapters.filters
title: Filter Nodes
section: Reference
order: 15
description: Nodes that create and apply Muscat element filters.
---

# Filter nodes

Both selectors expose optional `nFilter: Node Selector` and
`eFilter: Selector` input connectors. Connect a Node Selector's `filter` output
to `nFilter`, or an Element Selector's `filter` output to either `eFilter` or
`nFilter`. Element filters implement the node-filter interface: when used as
`nFilter`, they select the nodes used by their selected elements. FlowGraph
registers this one-way connection as an identity conversion, passing the same
filter object unchanged. A node filter cannot feed an element-only input.
These criteria intersect with the selector's own tags and zones. Types remain
distinct; existing Element Selector IDs and output types remain unchanged.

## Node Selector (`create-muscat-node-filter`)

Available under **Mesh Tools → Filters**. Creates `filter: Node Selector`, a
Muscat `NodeFilter`. Parameters `ntag=[]` and `etag=[]` are also optional inputs.
Node tags select their nodes; element tags and `eFilter` select nodes used by
those elements. Expandable `zone_1`, `zone_2`, … inputs accept up to 128 zones,
combined with OR; selected points have signed distance <= 0. Other criteria
intersect. Empty criteria select all nodes. There are no element dimensionality,
element-type or zone-treatment settings because this selector evaluates nodes.

`nFilter` further intersects selected node indices. FlowGraph uses a small
Muscat `NodeFilter` subclass to apply this criterion because the installed
upstream implementation stores `nFilter` without evaluating it. The output
can feed another selector's `nFilter`; Filter Mesh still requires an element
selector rather than a node selector.

## Element Selector (`create-muscat-element-filter`)

Creates `filter: Element filter`. Parameters (all default to `[]`) are
`dimensionality` (choices 0–3), `element_types` (Muscat element-type names),
`ntag` (node-tag names), and `etag` (element-tag names). Each parameter is also
an optional input port. Empty selections mean no restriction for that criterion.

`nFilterTreatment` controls how a connected `nFilter` selects elements:
`ALL_NODES` (default) requires every node, while `AT_LEAST_ONE` requires any
node. This setting is also an optional input port and is independent of
`zonesTreatment`. Connected `eFilter` intersects element selections directly.

Optional expandable `zone_1`, `zone_2`, … inputs (up to 128) accept **Zone**
outputs from the **Mesh Tools → Filters → Zones** submenu. Multiple zones are
combined with OR; tag/type/dimension criteria still intersect with the zone
selection. `zonesTreatment` selects `CENTER` (default), `ALL_NODES`, or
`AT_LEAST_ONE`. A point is inside when its signed distance is zero or negative.

## Filter Mesh (`filter-mesh-muscat`)

Requires `mesh: Mesh document` and `filter: Element filter`; emits
`mesh: Mesh document` containing the selected elements. Node fields are retained
on the filtered result. The operation extracts a new document and does not
change the input document.

## Zones

Each node creates a fresh Muscat implicit geometry and emits `zone: Zone`.
Numeric/vector/text parameters are optional input ports, so connected values
override local settings. Boolean checkboxes remain local. Mesh inputs are
required where shown below. Infrastructure base/cache/delayed-init/factory
classes and the mesh-conversion helper are not zone nodes.

| Node (ID) | Configuration and required inputs |
| --- | --- |
| Wrapped Field (`zone-wrapped`) | Signed-distance `field` list, default `[0.0]`; its length must match the evaluated nodes/centers. |
| External Surface (`zone-externalsurface`) | `mesh`; `method="bulk"` (`bulk` or `normal`), `offset=0.001`. |
| By Element Tag (`zone-byetag`) | `mesh`; `etags=[]`, `offset=0.0`. |
| By Element Tag II (`zone-byetagii`) | `mesh`; `etags=[]`, `offset=0.0`, `numberOfElementPseudoDistance=10`. See support restriction below. |
| Axis-Aligned Box (`zone-axisalignbox`) | `origin=[0,0,0]`, `size=[1,1,1]`. |
| Spheres From Node Tag (`zone-spherefromntag`) | `mesh`; `nTag=""`, `radius=1.0`. The tag must contain at least one node. |
| Sphere (`zone-sphere`) | `center=[0,0,0]`, `radius=1.0`. |
| Ellipse (`zone-ellipse`) | `center=[0,0,0]`, vector `radius=[1,1,1]`. |
| Cylinder (`zone-cylinder`) | `center1=[0,0,0]`, `center2=[1,0,0]`, `radius=1.0`, `wcups=True` (end caps). |
| Plane (`zone-plane`) | `point=[0,0,0]`, `normal=[1,0,0]`, `offset=0.0`. Normal is normalized. |
| Gyroid (`zone-gyroid`) | `scale=1.0`, `offset=[0,0,0]`, `type=0` (0–2), `wall=False`, `wallThickness=0.5`. |
| 60 Degree Walls (`zone-60d`) | `lx=1.0`, `w=0.1`. |
| Honeycomb (`zone-honeycomb`) | `lx=1.0`, `w=0.1`, `translate=[0,0,0]`. |
| STL Surface (`zone-stl`) | `filename` file parameter/input; loads an existing surface file. |
| Analytical (`zone-analytical`) | `expression="x"`; requires SymPy (already a Muscat dependency). **Trusted expressions only**: Muscat delegates parsing to SymPy; this is not a sandbox. |
| Holes (`zone-holes`) | `mesh`; `r=0.5`, integer-vector `n=[3,3,3]`, `offset=[0,0,0]`, `type="Aligned"` (`Aligned`, `Original`, `Staggered`). |
| Union (`zone-union`) | Expandable `zone_1`, … inputs, at least one required at execution; `smoothControl=0.0`. |
| Intersection (`zone-intersection`) | Expandable `zone_1`, … inputs, at least one required at execution; `smoothControl=0.0`. |
| Difference (`zone-difference`) | Required `zone1`, `zone2`; subtracts zone2 from zone1; `smoothControl=0.0`. |
| Offset (`zone-offset`) | Required `zone`; `offset=0.0`. Positive shrinks, negative grows. |
| Inside Out (`zone-insideout`) | Required `zone`; reverses the signed distance. |
| Symmetric (`zone-symmetric`) | Required `zone`; `center=[0,0,0]`; folds points into the positive octant about the center. |
| Shell (`zone-shell`) | Required `zone`; `thickness=0.1`; follows Muscat's level-set shell convention. |
| Transform (`zone-transform`) | Required `zone`; `offset=[0,0,0]`, `first=[1,0,0]`, `second=[0,1,0]`; uses Muscat's inverse coordinate transform (offset is the coordinate-frame offset, not a world-space translation). |

Vectors must have three finite components. Radii, box sizes, scales, lattice
periods, hole counts and pseudo-distance counts must be positive. Normals and
transform axes cannot be degenerate, and cylinder endpoints must differ.

**Support-bound fields:** Wrapped Field and By Element Tag II are Muscat field
objects, not general pointwise signed-distance functions. Wrapped Field values
must match the evaluated array length; use node-based treatment when wrapping
node values. By Element Tag II evaluates only on its support nodes; use it with
the same mesh and `ALL_NODES` or `AT_LEAST_ONE`, not `CENTER` or point-transform
operators. Its tags must define an inside/outside interface. General distance
objects such as Sphere, Plane and By Element Tag work with all treatments.

Example: connect **Sphere → Element Selector `zone_1` → Filter Mesh `filter`**,
and connect the source mesh to Filter Mesh `mesh`. Insert Union, Difference,
Offset or another operator between geometry nodes and the selector to compose
spatial selections. Zone configuration and connections persist in workflow JSON;
runtime Muscat objects are recreated when executing the workflow.