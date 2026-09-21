"""The canonical, editable mesh document."""

from dataclasses import dataclass, field

import numpy as np
from Muscat.MeshContainers.Mesh import Mesh
from Muscat.Types import MuscatIndex


@dataclass
class MeshDocument:
    """Own a Muscat mesh and application-level state without UI dependencies."""

    mesh: Mesh  # type: ignore # this is only a type hint

    _mesh: Mesh = field(init=False, repr=False)

    def __str__(self):
        return str(self._mesh)

    @property
    def mesh(self) -> Mesh:
        return self._mesh

    @mesh.setter
    def mesh(self, mesh: Mesh):
        self._mesh = mesh
        # ensure we have the correct FlowGraph Fields
        self.get_muscat_node_ids()
        self.get_muscat_elements_ids()

    def get_muscat_node_ids(self):

        if "flowgraph_node_id" not in self.mesh.nodeFields:
            res = np.arange(self.mesh.GetNumberOfNodes(), dtype=MuscatIndex)
            self.mesh.nodeFields["flowgraph_node_id"] = res
        else:
            res = self.mesh.nodeFields["flowgraph_node_id"]

        if len(res) != self.mesh.GetNumberOfNodes():
            raise ValueError("MeshDocument node IDs do not match its Muscat mesh")
        return res

    def get_muscat_elements_ids(self):
        if "flowgraph_element_id" not in self.mesh.elemFields:
            res = np.arange(self.mesh.GetNumberOfElements(), dtype=MuscatIndex)
            self.mesh.elemFields["flowgraph_element_id"] = res
        else:
            res = self.mesh.elemFields["flowgraph_element_id"]

        if len(res) != self._mesh.GetNumberOfElements():
            raise ValueError("MeshDocument element IDs do not match its Muscat mesh")
        return res

    def to_vtk_unstructured_grid(self):  # type: ignore[no-untyped-def]
        """Create a VTK projection with stable Muscat node and element ID arrays."""
        from Muscat.Bridges.vtkBridge import MeshToVtk

        return MeshToVtk(self.mesh)

    def __repr__(self):
        mesh = self.mesh
        res = f"""Mesh details       :
Number Of Nodes    : {mesh.GetNumberOfNodes()}

"""

        if len(mesh.nodesTags):
            res += " Nodes named selections (name: size):\n"
            for x in mesh.nodesTags:
                res += f"  {x.name}: {len(x)} \n"

        res += f"Total Number Of Elements : {mesh.GetNumberOfElements()} \n"

        for data in mesh.elements.values():
            res += f" Element type: {data.elementType} \n"
            res += f"  Number of elements: {data.GetNumberOfElements()}\n"
            if len(data.tags):
                res += "  Named selections (name: size):\n"
                for x in data.tags:
                    res += f"   {x.name}: {len(x)} \n"

        if len(mesh.nodeFields.keys()) > 0:
            res += "\n  Node Fields (name: type, shape):\n"
            for k, v in mesh.nodeFields.items():
                res += f"   {k}: {v.dtype}, {v.shape}\n"
        if len(mesh.elemFields.keys()) > 0:
            res += "\n  Element Fields (name: type, shape):\n"
            for k, v in mesh.elemFields.items():
                res += f"   {k}: {v.dtype}, {v.shape}\n"
        return res
