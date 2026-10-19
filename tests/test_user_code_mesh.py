"""MeshDocument ports and values in a typed User Function."""

from Muscat.MeshContainers.Mesh import Mesh

from flowgraph.adapters.user_code import USER_FUNCTION
from flowgraph.domain.mesh_document import MeshDocument


def test_user_function_mesh_document_ports_and_execution() -> None:
    code = "def Execute(mesh: MeshDocument) -> tuple[MeshDocument]:\n    return (mesh,)\n"
    instance = USER_FUNCTION.create_instance("python", parameters={"code": code})
    ports = USER_FUNCTION.ports_for_instance(instance)
    assert [(port.name, port.data_type.id) for port in ports] == [
        ("mesh", "mesh-document"),
        ("output1", "mesh-document"),
    ]
    mesh = MeshDocument(Mesh())
    assert USER_FUNCTION.executor({"mesh": mesh}, {"code": code}) == {"output1": mesh}
