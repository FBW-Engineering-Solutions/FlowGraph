"""Regression tests for the headless workflow import boundary."""

from __future__ import annotations

import subprocess
import sys


def test_headless_registry_includes_control_nodes_without_gui_runtime_imports() -> None:
    script = """
from flowgraph.application.node_registry import create_node_registry
registry = create_node_registry()
assert registry.require('float-slider').presentation == 'slider'
assert registry.require('int-slider').presentation == 'slider'
assert registry.require('show-value')
assert registry.require('mesh-sink')
import sys
assert not any(name == 'trame' or name.startswith(('trame_', 'vtk', 'webview')) for name in sys.modules)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
