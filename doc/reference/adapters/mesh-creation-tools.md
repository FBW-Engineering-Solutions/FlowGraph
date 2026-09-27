---
id: reference.adapters.mesh-creation-tools
title: Mesh Creation Tool Nodes
section: Reference
order: 15
description: Nodes wrapping Muscat.MeshTools.MeshCreationTools.
---

# Mesh creation tool nodes

These nodes wrap Muscat's `MeshCreationTools` functions. Mesh inputs and outputs use
FlowGraph `Mesh document` values. Boolean options are UI-only checks and are not
connectable ports.

| Node (ID) | Inputs and outputs | Parameters/defaults |
| --- | --- | --- |
| **Create Uniform Mesh Of Bars** (`create-uniform-mesh-of-bars`) | Output `mesh: Mesh document` | `startPoint=0.0`, `stopPoint=1.0`, `nbPoints=50`, `secondOrder=False` |
| **Create Mesh Of Triangles** (`create-mesh-of-triangles`) | Inputs `points`, `triangles`; output `mesh` | None |
| **Create Mesh Of** (`create-mesh-of`) | Inputs `points`, `connectivity`; output `mesh` | `elemName="Triangle_3"` |
| **Create Square** (`create-square`) | Output `mesh` | `dimensions=[2,2]`, `origin=[-1,-1]`, `spacing=[1,1]`, `ofTriangles=False` |
| **Create Disk** (`create-disk`) | Output `mesh` | `nr=10`, `nTheta=10`, `r0=0.5`, `r1=1.0`, `theta0=0`, `theta1=pi/2`, `ofTriangles=False` |
| **Create Cube** (`create-cube`) | Output `mesh` | `dimensions=[2,2,2]`, `origin=[-1,-1,-1]`, `spacing=[1,1,1]`, `ofTetras=False` |
| **Create Mesh From Cells Dict** (`create-mesh-from-cells-dict`) | Inputs `points`, `cellsDict`, `pointFields`, `cellFields`, `originalIds`, `cellsOriginalIds`; output `mesh` | `cellFieldInDictOrder=True` |
| **Mesh To Simplex** (`mesh-to-simplex`) | Input/output `mesh: Mesh document` | `inPlace=True` |
| **To Quadratic Mesh** (`to-quadratic-mesh`) | Input `inputMesh`; output `outputMesh` | None |
| **Quad To Lin (Creation Tools)** (`quad-to-lin-creation`) | Input `inputMesh`; output `outputMesh` | `divideQuadElements=True`, `linearizedMiddlePoints=False` |
| **Mirror Mesh** (`mirror-mesh`) | Input/output `inmesh: Mesh document` | `x=None`, `y=None`, `z=None`, `propagateToNodeFields=False` |
| **Create 0D Elements For Every Point** (`create-0d-elements-for-every-point`) | Input `mesh`; output `elements: Elements container` | None |
| **Subdivide Mesh** (`subdivide-mesh`) | Input/output `mesh: Mesh document` | `level=1` |