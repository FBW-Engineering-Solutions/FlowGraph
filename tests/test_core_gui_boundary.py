"""Regression tests for the GUI-free FlowGraph core package boundary."""

from __future__ import annotations

import subprocess
import sys


def test_core_cli_and_registry_do_not_import_desktop_dependencies() -> None:
    """Import core entry points without loading Trame, VTK, PyWebView, or desktop UI modules."""
    script = """
from flowgraph.core_cli import build_parser
from flowgraph.application.node_registry import create_node_registry
build_parser()
create_node_registry()
import sys
forbidden = ('trame', 'trame_', 'vtk', 'webview', 'flowgraph.ui')
assert not any(name == prefix or name.startswith(prefix) for name in sys.modules for prefix in forbidden)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
