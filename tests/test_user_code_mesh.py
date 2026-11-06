"""MeshDocument ports and values in a typed User Function."""

from Muscat.MeshContainers.Mesh import Mesh

from flowgraph.adapters.user_code import DEFAULT_CODE, USER_FUNCTION
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


def test_default_user_function_warns_about_readonly_inputs_and_preserves_aliases() -> None:
    assert "WARNING: Inputs are read-only" in DEFAULT_CODE
    assert "Never modify inputs or their nested data in place" in DEFAULT_CODE
    assert "Inputs are read-only" in USER_FUNCTION.description
    instance = USER_FUNCTION.create_instance("default")
    assert [port.name for port in USER_FUNCTION.ports_for_instance(instance)] == [
        "input1",
        "input2",
        "input3",
        "output1",
        "output2",
        "output3",
    ]
    values = {"input1": [1], "input2": {"nested": [2]}, "input3": [3]}
    outputs = USER_FUNCTION.executor(values, instance.parameters)
    for index, value in enumerate(values.values(), 1):
        assert outputs[f"output{index}"] is value
    assert values == {"input1": [1], "input2": {"nested": [2]}, "input3": [3]}
