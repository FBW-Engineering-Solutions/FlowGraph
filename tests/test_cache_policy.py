"""Cache policy inference is schema-based; explicit overrides always win."""

from dataclasses import replace

import pytest

from flowgraph.adapters.data_types import FILE, STRING, ParameterKind
from flowgraph.application.file_dependencies import single_file_dependency
from flowgraph.application.workflow_core import (
    NodeDefinition,
    NodeRegistry,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
    WorkflowGraph,
)
from flowgraph.application.workflow_session import WorkflowSession
from flowgraph.domain.filepath import FilePath


def definition(**kwargs):
    return NodeDefinition("test", "", "Test", (), lambda _i, _p: {}, **kwargs)


def test_default_pure_and_custom_dependency_inference():
    assert definition().cache_policy == "pure"
    resolver = lambda _i, _p: "revision"
    item = definition(cache_dependencies=resolver)
    assert item.cache_policy == "external"
    assert item.cache_dependencies is resolver
    with pytest.raises(ValueError, match="requires a dependency resolver"):
        definition(cache_policy="external")
    with pytest.raises(ValueError, match="cache_policy must"):
        definition(cache_policy="invalid")


@pytest.mark.parametrize("kind", [FILE, ParameterKind.SELECT_SERVER_FILENAME])
def test_declared_file_parameter_infers_external(kind, tmp_path):
    path = tmp_path / "data"
    path.write_text("first")
    item = definition(parameters=(ParameterDefinition("source_file", kind, "Source", str(path)),))
    assert item.cache_policy == "external"
    before = item.cache_dependencies({}, item.default_parameters)
    path.write_text("other")
    assert item.cache_dependencies({}, item.default_parameters) != before


def test_typed_file_input_is_inferred_but_outputs_and_string_paths_are_not(tmp_path):
    path = tmp_path / "data"
    path.write_text("first")
    base = definition()
    item = replace(
        base, cache_policy=None, ports=(PortDefinition("source", PortDirection.INPUT, FILE),)
    )
    assert item.cache_policy == "external"
    assert item.cache_dependencies({"source": FilePath(path)}, {})
    output = replace(
        base, cache_policy=None, ports=(PortDefinition("path", PortDirection.OUTPUT, FILE),)
    )
    text_input = replace(
        base, cache_policy=None, ports=(PortDefinition("path", PortDirection.INPUT, STRING),)
    )
    assert output.cache_policy == text_input.cache_policy == "pure"


def test_path_uses_single_file_helper_and_connected_value_overrides_parameter(tmp_path):
    path = tmp_path / "data"
    path.write_text("first")
    item = definition(parameters=(ParameterDefinition("path", FILE, "Path", "missing"),))
    assert item.cache_dependencies is single_file_dependency
    assert item.cache_dependencies({"path": path}, item.default_parameters)
    with pytest.raises(FileNotFoundError):
        item.cache_dependencies({}, item.default_parameters)
    path.unlink()
    with pytest.raises(FileNotFoundError):
        item.cache_dependencies({"path": path}, item.default_parameters)


def test_multiple_declared_files_and_explicit_companions_are_fingerprinted(tmp_path):
    first, second, third = (tmp_path / name for name in ("first", "second", "third"))
    for path in (first, second, third):
        path.write_text("original")
    item = definition(
        parameters=(
            ParameterDefinition("a", FILE, "A", str(first)),
            ParameterDefinition("b", FILE, "B", str(second)),
        )
    )
    values = {"a": FilePath([first, third]), "b": str(second)}
    before = item.cache_dependencies({}, values)
    third.write_text("changed")
    assert item.cache_dependencies({}, values) != before
    paths = FilePath([first, third])
    before = single_file_dependency({"path": paths}, {})
    third.write_text("changed again")
    assert single_file_dependency({"path": paths}, {}) != before


@pytest.mark.parametrize("policy", ["pure", "always", "composite"])
def test_explicit_policy_wins_over_file_inference(policy):
    item = definition(
        cache_policy=policy, parameters=(ParameterDefinition("path", FILE, "Path", "missing"),)
    )
    assert item.cache_policy == policy
    assert item.cache_dependencies is None


@pytest.mark.parametrize("policy", ["pure", "always"])
def test_explicit_nonexternal_policy_never_fingerprints_files(policy):
    def forbidden(_inputs, _parameters):
        raise AssertionError("Explicit override must not poll external dependencies")

    item = definition(cache_policy=policy, cache_dependencies=forbidden)
    registry = NodeRegistry()
    registry.register(item)
    graph = WorkflowGraph([item.create_instance("node")], [])
    session = WorkflowSession(registry)
    session.run(graph)
    session.run(graph)
    assert session.metadata["reused"] == (["node"] if policy == "pure" else [])


def test_inferred_file_reader_reuses_and_reexecutes_on_content_changes(tmp_path):
    path = tmp_path / "data"
    path.write_text("first")
    calls = []

    def read(_inputs, parameters):
        calls.append("read")
        return {"text": path.read_text()}

    item = NodeDefinition(
        "reader",
        "",
        "Reader",
        (PortDefinition("text", PortDirection.OUTPUT, STRING),),
        read,
        parameters=(ParameterDefinition("path", FILE, "Path", str(path)),),
    )
    registry = NodeRegistry()
    registry.register(item)
    graph = WorkflowGraph([item.create_instance("node")], [])
    session = WorkflowSession(registry)
    session.run(graph)
    session.run(graph)
    assert calls == ["read"]
    path.write_text("other")
    assert session.run(graph).node_outputs["node"]["text"] == "other"
    assert calls == ["read", "read"]


def test_builtin_computations_and_exception_classification():
    from flowgraph.adapters.files import READ_DIRECTORY_FILES, SELECT_FILE, SELECT_SERVER_FILE
    from flowgraph.adapters.image_tools import READ_IMAGE, WRITE_IMAGE
    from flowgraph.adapters.readers import (
        LOAD_CSV,
        LOAD_MESHIO,
        LOAD_MESHLANE,
        LOAD_MUSCAT,
        READ_TABLE,
    )
    from flowgraph.adapters.remote_files import DOWNLOAD_URL
    from flowgraph.adapters.table_tools import AGGREGATE_LISTS_TO_TABLE, MESH_TO_TABLE
    from flowgraph.adapters.user_code import USER_FUNCTION
    from flowgraph.adapters.workflow import RUN_WORKFLOW
    from flowgraph.adapters.writers import WRITE_MESHIO, WRITE_MESHLANE, WRITE_MUSCAT, WRITE_TABLE

    for item in (AGGREGATE_LISTS_TO_TABLE, MESH_TO_TABLE, SELECT_FILE, SELECT_SERVER_FILE):
        assert item.cache_policy == "pure"
        assert item.cache_dependencies is None
    for item in (READ_IMAGE, READ_TABLE, LOAD_CSV, LOAD_MUSCAT, LOAD_MESHIO, LOAD_MESHLANE):
        assert item.cache_policy == "external"
        assert item.cache_dependencies is single_file_dependency
    for item in (
        WRITE_IMAGE,
        WRITE_TABLE,
        WRITE_MUSCAT,
        WRITE_MESHIO,
        WRITE_MESHLANE,
        READ_DIRECTORY_FILES,
        USER_FUNCTION,
        DOWNLOAD_URL,
    ):
        assert item.cache_policy == "always"
    assert RUN_WORKFLOW.cache_policy == "composite"
