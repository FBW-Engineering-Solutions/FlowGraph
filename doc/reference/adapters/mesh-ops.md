---
id: reference.adapters.mesh-ops
title: Mesh Operation Nodes
section: Reference
order: 16
description: Nodes for coordinate transforms, tetrahedralization, and tags.
---

# Mesh-operation nodes

| Node (ID) | Inputs and outputs | Parameters/defaults |
| --- | --- | --- |
| **Mesh Transform** (`transform`) | Outputs `Transform` | `translation=[0,0,0]`, `first=[1,0,0]`, `second=[0,1,0]`; `keepNormalized=True`, `keepOrthogonal=True` (the last two are UI-only). |
| **Apply Transform** (`apply-transform`) | Inputs `mesh: Mesh document`, `Transform: Transform`; output `mesh: Mesh document` | `onVectorFields=True`, `inverse=False` (UI-only). |
| **Delaunay 3D** (`delaunay-3d`) | Input/output `meshDocument: Mesh document` | None |
| **Remove Lonely Nodes** (`remove-lonely-nodes`) | Input/output `mesh: Mesh document` | None |
| **Quad To Lin** (`quad-to-lin`) | Input `inputMesh: Mesh document`; output `outputMesh: Mesh document` | `divideQuadElements=True`, `linearizedMiddlePoints=False` (UI-only) |
| **Remesh** (`remesh`) | Input `mesh: Mesh document`; optional `levelset`, `solution`, `metric: Any`; output `mesh: Mesh document` | `backend="MmgInMemory"`, `remesherOptions="{}"`, `backendOptions="{}"` (local settings) |
| **Rename Tag** (`rename-tag`) | Input/output `mesh: Mesh document` | `entity="element"`, `tag=""`, `newTag=""` |
| **Merge Tags** (`merge-tags`) | Input/output `mesh: Mesh document` | `entity="element"`, `sourceTags=[]`, `targetTag="merged"` |
| **Remove Tag** (`remove-tag`) | Input/output `mesh: Mesh document` | `entity="element"`, `tag=""` |
| **Create Tag** (`create-tag`) | Inputs `mesh: Mesh document`, `filter: Element filter`; output `mesh: Mesh document`; `tagName: Text` is also an input port | `tagName=""`; `nodeTag=False` (UI-only checkbox) |

Transform vector parameters are optional input ports. Apply Transform copies the
input and can apply the inverse transform; when enabled, 3-component node and
element vector fields are transformed in the inverse direction too. Delaunay 3D
creates tetrahedra from the document's points. Tag operations support `element`
or `node`, validate tag names, and return a copied document.
Create Tag copies the input document and applies the selected element filter to
create either an element tag or, when `nodeTag=True`, a node tag containing the
nodes used by the selected elements.
Quad To Lin delegates to Muscat's `QuadToLin` operation. It converts supported
quadratic elements to linear elements, optionally subdividing them and
linearizing their middle points. As in Muscat, mesh fields are not preserved.

Remove Lonely Nodes is available under **Mesh Tools → Mesh Ops**. It removes
points not referenced by any element and remaps connectivity to the remaining
points. Node fields (including FlowGraph IDs), original node IDs and node tags
are filtered consistently; element fields, element IDs and element tags are
retained. The input document is unchanged. A mesh with no elements loses all
its points; a mesh with no unused points retains its topology and metadata.

Remesh delegates to Muscat's remesher using the selected `MmgInMemory` (default)
or `mmg` backend. Optional `levelset`, `solution`, and `metric` inputs override
matching mesh node fields when connected. The remesher and backend options must
each be JSON objects. The operation returns a new mesh document; it requires a
working remeshing backend in the local environment.

## Boundary, inspection, and cleanup

These nodes leave inputs unchanged and publish read-only array views, sharing
unchanged buffers rather than copying them.

| Node (ID) | Contract |
| --- | --- |
| **Extract Skin** (`extract-skin`) | `mesh` → `mesh`. Connectable integer `dimensionality=-1` selects the highest element dimension automatically; explicit values are 1, 2, 3. |
| **Mesh Measure** (`mesh-measure`) | `mesh`, optional element `filter` → Float `measure`. Defaults to the highest element dimension. Empty selections return zero; mixed-dimensional selections are rejected. |
| **Element Measures** (`element-measures`) | `mesh`, optional element `filter` → read-only 1D arrays `measures`, `indices`. Without a selector includes all dimensions. |
| **Element Centers** (`element-centers`) | `mesh` → read-only 2D array `centers` in global element order: arithmetic means of element node coordinates. |
| **Merge Duplicate Nodes** (`merge-duplicate-nodes`) | `mesh` → `mesh`, read-only integer `indices` of retained source nodes. Connectable Float `tolerance=0.0`: exact matching; positive finite values merge nearby nodes. |
| **Remove Duplicate Elements** (`remove-duplicate-elements`) | `mesh` → `mesh`. Equal node sets within each element type are duplicates, including permutations. |

Skin retains all source nodes, original node IDs, nodal fields and node tags.
It creates a `Skin` element tag and fresh positional FlowGraph element IDs;
source element fields/tags do not transfer. Empty or point-only meshes are
rejected. Use **Remove Lonely Nodes** afterward to compact the boundary.

Measures are lengths (1D), areas (2D), or volumes (3D). Element Measures pairs
values with **global positional indices**, not stored `flowgraph_element_id`
values. Filtered results are compact, not full-mesh fields. Mixed-dimensional
outputs may have different units: select one dimension before summing. The full
mesh measure array is evaluated before gathering a selection for reliable alignment.

Duplicate-node cleanup remaps connectivity/tags and retains representative nodal
fields and original/FlowGraph IDs without averaging conflicts. Duplicate-element
cleanup merges tags and keeps the first duplicate's fields and original ID.
Output order follows Muscat connectivity ordering; IDs need not be contiguous.
Node merging may create duplicate elements: chain both cleanup nodes if needed.
Neither cleanup implicitly removes unused nodes.