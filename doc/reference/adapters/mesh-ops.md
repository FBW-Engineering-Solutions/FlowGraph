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

Remesh delegates to Muscat's remesher using the selected `MmgInMemory` (default)
or `mmg` backend. Optional `levelset`, `solution`, and `metric` inputs override
matching mesh node fields when connected. The remesher and backend options must
each be JSON objects. The operation returns a new mesh document; it requires a
working remeshing backend in the local environment.