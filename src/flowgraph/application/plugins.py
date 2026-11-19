"""Explicit, trusted Python-file plugins for native workflow hosts."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from collections.abc import Sequence
from pathlib import Path

from flowgraph.adapters import AdapterGroup
from flowgraph.application.workflow_core import NodeDefinition


class PluginError(ValueError):
    """A configured plugin could not be imported or has an invalid export."""


def resolve_plugin_paths(paths: Sequence[str | Path]) -> tuple[Path, ...]:
    """Resolve explicit files against the caller's cwd, before workers change it."""
    resolved = []
    for value in paths:
        path = Path(value).expanduser().resolve()
        if path.suffix != ".py" or not path.is_file():
            raise PluginError(f"Plugin '{path}': expected an existing Python (.py) file")
        if path in resolved:
            raise PluginError(f"Plugin '{path}': file was supplied more than once")
        resolved.append(path)
    return tuple(resolved)


def load_plugin_groups(paths: Sequence[str | Path]) -> tuple[AdapterGroup, ...]:
    """Import files exporting AVAILABLE_NODES; cache successful imports per process.

    This executes arbitrary trusted Python. No plugin paths are read from workflow
    JSON, and no directories are added to Python's import search path. Dependencies
    must already be importable in the host environment. Restart to reload code.
    """
    groups = []
    for path in resolve_plugin_paths(paths):
        name = "_flowgraph_plugin_" + hashlib.sha256(str(path).encode()).hexdigest()
        module = sys.modules.get(name)
        try:
            if module is None:
                spec = importlib.util.spec_from_file_location(name, path)
                if spec is None or spec.loader is None:
                    raise ValueError("cannot create a Python module for this file")
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
            definitions = tuple(module.AVAILABLE_NODES)
            if any(not isinstance(item, NodeDefinition) for item in definitions):
                raise ValueError("AVAILABLE_NODES must contain only NodeDefinition objects")
            # Materialize one-shot iterators so later registries see the same nodes.
            module.AVAILABLE_NODES = definitions
        except (Exception, SystemExit) as error:
            sys.modules.pop(name, None)
            raise PluginError(f"Plugin '{path}': {type(error).__name__}: {error}") from error
        groups.append(AdapterGroup(f"Plugins / {path.name}", definitions))
    return tuple(groups)
