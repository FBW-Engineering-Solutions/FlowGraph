"""Command contracts for future undoable mesh changes."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    """Describe an application command outcome without binding it to the UI."""

    changed_entity_count: int = 0
    requires_vtk_refresh: bool = False
    requires_validation: bool = False
    warnings: tuple[str, ...] = ()
