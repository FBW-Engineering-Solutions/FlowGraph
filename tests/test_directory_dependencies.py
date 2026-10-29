"""Recursive metadata dependencies never reuse incomplete directory snapshots."""

import os
from contextlib import contextmanager

import pytest

from flowgraph.adapters.data_types import FILE, STRING
from flowgraph.application.file_dependencies import (
    declared_dependency_metadata,
    declared_file_dependencies,
    single_file_dependency,
)
from flowgraph.application.workflow_core import (
    NodeDefinition,
    NodeRegistry,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
    WorkflowEdge,
    WorkflowGraph,
)
from flowgraph.application.workflow_session import WorkflowSession
from flowgraph.domain.filepath import FilePath


def directory_session(path, read=None):
    reader = NodeDefinition(
        "reader",
        "",
        "Reader",
        (PortDefinition("value", PortDirection.OUTPUT, STRING),),
        read or (lambda _i, _p: {"value": "directory result"}),
        parameters=(ParameterDefinition("path", FILE, "Path", str(path)),),
    )
    downstream = NodeDefinition(
        "downstream",
        "",
        "Downstream",
        (
            PortDefinition("value", PortDirection.INPUT, STRING),
            PortDefinition("value", PortDirection.OUTPUT, STRING),
        ),
        lambda inputs, _p: {"value": inputs["value"]},
    )
    registry = NodeRegistry()
    registry.register(reader)
    registry.register(downstream)
    graph = WorkflowGraph(
        [reader.create_instance("reader"), downstream.create_instance("downstream")],
        [WorkflowEdge("reader", "value", "downstream", "value")],
    )
    return WorkflowSession(registry), graph


@pytest.mark.parametrize("change", ["add", "remove", "rename", "timestamp", "size"])
def test_nested_file_changes_invalidate_reader_and_downstream(tmp_path, change):
    nested = tmp_path / "sub" / "deeper"
    nested.mkdir(parents=True)
    source = nested / "data"
    source.write_text("original")
    session, graph = directory_session(tmp_path)
    session.run(graph)
    assert not session.run(graph).execution_order
    if change == "add":
        (nested / "added").write_text("new")
    elif change == "remove":
        source.unlink()
    elif change == "rename":
        source.rename(nested / "renamed")
    elif change == "timestamp":
        info = source.stat()
        os.utime(source, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))
    else:
        info = source.stat()
        source.write_text("different size")
        os.utime(source, ns=(info.st_atime_ns, info.st_mtime_ns))
    assert session.run(graph).execution_order == ("reader", "downstream")
    assert not session.run(graph).execution_order


def test_empty_directory_and_empty_subfolders(tmp_path):
    session, graph = directory_session(tmp_path)
    session.run(graph)
    assert not session.run(graph).execution_order
    (tmp_path / "empty").mkdir()
    assert not session.run(graph).execution_order
    (tmp_path / "empty" / "first").touch()
    assert session.run(graph).execution_order == ("reader", "downstream")


def test_directory_snapshots_do_not_read_contents_and_use_relative_names(tmp_path, monkeypatch):
    nested = tmp_path / "sub"
    nested.mkdir()
    source = nested / "data"
    source.write_text("first")
    info = source.stat()
    before = single_file_dependency({"path": tmp_path}, {})
    assert before[-1] == (("sub/data", info.st_mtime_ns, info.st_size),)
    source.write_text("other")
    os.utime(source, ns=(info.st_atime_ns, info.st_mtime_ns))

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Directory dependencies must not read file contents")

    monkeypatch.setattr(type(source), "open", forbidden)
    assert single_file_dependency({"path": tmp_path}, {}) == before
    assert declared_dependency_metadata(single_file_dependency, {"path": tmp_path}, {})


def test_directory_limit_boundary_overflow_and_recovery(tmp_path):
    nested = tmp_path / "sub"
    nested.mkdir()
    for index in range(1000):
        (nested / str(index)).touch()
    session, graph = directory_session(tmp_path)
    session.run(graph)
    assert not session.run(graph).execution_order
    extra = tmp_path / "extra"
    extra.touch()
    with pytest.raises(ValueError, match="exceeds 1000 files"):
        single_file_dependency({"path": tmp_path}, {})
    for _ in range(2):
        assert session.run(graph).execution_order == ("reader", "downstream")
        assert not session.entries
    extra.unlink()
    session.run(graph)
    assert not session.run(graph).execution_order


def test_directory_changes_during_execution_are_not_retained(tmp_path):
    def read(_inputs, _parameters):
        (tmp_path / "created").write_text("new")
        return {"value": "result"}

    session, graph = directory_session(tmp_path, read)
    session.run(graph)
    assert not session.entries


def test_overflow_stops_scanning_at_first_untracked_file(tmp_path, monkeypatch):
    for index in range(1005):
        (tmp_path / str(index)).touch()
    visited = []

    @contextmanager
    def counted(path):
        with os.scandir(path) as entries:

            def tracked_entries():
                for entry in entries:
                    visited.append(entry.name)
                    yield entry

            yield tracked_entries()

    monkeypatch.setattr("flowgraph.application.file_dependencies.scandir", counted)
    with pytest.raises(ValueError, match="exceeds 1000 files"):
        single_file_dependency({"path": tmp_path}, {})
    assert len(visited) == 1001


def test_arbitrary_declared_names_connected_values_and_companions(tmp_path):
    directory = tmp_path / "directory"
    directory.mkdir()
    companion = tmp_path / "companion"
    companion.write_text("first")
    resolver = declared_file_dependencies(("source",))
    inputs = {"source": FilePath([directory, companion])}
    parameters = {"source": "missing"}
    before = resolver(inputs, parameters)
    metadata = declared_dependency_metadata(resolver, inputs, parameters)
    (directory / "new").touch()
    assert resolver(inputs, parameters) != before
    assert declared_dependency_metadata(resolver, inputs, parameters) != metadata
    before = resolver(inputs, parameters)
    companion.write_text("changed")
    assert resolver(inputs, parameters) != before


@pytest.mark.parametrize("kind", ["symlink", "cycle", "fifo", "unreadable"])
def test_unsafe_directory_trees_are_uncacheable(tmp_path, monkeypatch, kind):
    if kind == "symlink":
        (tmp_path / "link").symlink_to(tmp_path / "missing")
    elif kind == "cycle":
        (tmp_path / "cycle").symlink_to(tmp_path, target_is_directory=True)
    elif kind == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("Named pipes are unavailable on this platform")
        os.mkfifo(tmp_path / "pipe")
    else:

        def denied(_path):
            raise PermissionError("unreadable directory")

        monkeypatch.setattr("flowgraph.application.file_dependencies.scandir", denied)
    session, graph = directory_session(tmp_path)
    for _ in range(2):
        assert session.run(graph).execution_order == ("reader", "downstream")
        assert not session.entries
