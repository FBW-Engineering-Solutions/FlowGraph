"""Snapshot-based undo and redo support for editable workflow graphs."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkflowHistoryEntry:
    """One reversible workflow edit represented by complete graph snapshots.

    Parameters
    ----------
    label:
        Short user-facing description of the recorded edit.
    before:
        JSON-compatible workflow state before the edit.
    after:
        JSON-compatible workflow state after the edit.
    """

    label: str
    before: dict[str, Any]
    after: dict[str, Any]


class WorkflowHistory:
    """Maintain a linear undo/redo history for serializable workflow snapshots."""

    def __init__(self) -> None:
        self._entries: list[WorkflowHistoryEntry] = []
        self._index = 0

    @property
    def can_undo(self) -> bool:
        """Return whether an earlier workflow state can be restored."""
        return self._index > 0

    @property
    def can_redo(self) -> bool:
        """Return whether an undone workflow state can be reapplied."""
        return self._index < len(self._entries)

    def clear(self) -> None:
        """Discard all recorded states."""
        self._entries.clear()
        self._index = 0

    def record(self, label: str, before: dict[str, Any], after: dict[str, Any]) -> bool:
        """Record a changed workflow state and discard its obsolete redo branch.

        Parameters
        ----------
        label:
            Short description of the edit.
        before:
            JSON-compatible workflow state before the edit.
        after:
            JSON-compatible workflow state after the edit.

        Returns
        -------
        bool
            ``True`` when the states differed and an entry was recorded.
        """
        if before == after:
            return False
        self._entries[self._index :] = []
        self._entries.append(WorkflowHistoryEntry(label, deepcopy(before), deepcopy(after)))
        self._index += 1
        return True

    def undo(self) -> WorkflowHistoryEntry | None:
        """Step backward and return the entry whose previous state should be restored."""
        if not self.can_undo:
            return None
        self._index -= 1
        return self._entries[self._index]

    def redo(self) -> WorkflowHistoryEntry | None:
        """Step forward and return the entry whose next state should be restored."""
        if not self.can_redo:
            return None
        entry = self._entries[self._index]
        self._index += 1
        return entry
