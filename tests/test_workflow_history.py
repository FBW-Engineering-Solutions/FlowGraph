"""Tests for workflow undo and redo history state."""

from flowgraph.application.workflow_history import WorkflowHistory


def test_history_undo_redo_and_branch_replacement() -> None:
    history = WorkflowHistory()
    initial = {"nodes": []}
    first = {"nodes": [{"id": "first"}]}
    second = {"nodes": [{"id": "second"}]}

    assert not history.can_undo
    assert not history.can_redo
    assert history.record("Add first", initial, first)
    assert history.can_undo
    assert not history.can_redo

    entry = history.undo()

    assert entry is not None
    assert entry.before == initial
    assert not history.can_undo
    assert history.can_redo

    assert history.record("Add second", initial, second)
    assert not history.can_redo
    entry = history.undo()
    assert entry is not None
    assert entry.after == second


def test_history_skips_identical_states_and_copies_recorded_snapshots() -> None:
    history = WorkflowHistory()
    before = {"nodes": []}
    after = {"nodes": [{"id": "node"}]}

    assert not history.record("No change", before, before)
    assert history.record("Add node", before, after)
    after["nodes"][0]["id"] = "changed-after-recording"

    entry = history.undo()

    assert entry is not None
    assert entry.after == {"nodes": [{"id": "node"}]}


def test_history_keeps_only_the_50_most_recent_entries() -> None:
    history = WorkflowHistory()

    for index in range(51):
        before = {"value": index}
        after = {"value": index + 1}
        assert history.record(f"Edit {index}", before, after)

    assert len(history._entries) == 50

    entry = history.undo()
    assert entry is not None
    assert entry.label == "Edit 50"
    assert entry.before == {"value": 50}

    for _ in range(49):
        assert history.undo() is not None
    assert not history.can_undo
