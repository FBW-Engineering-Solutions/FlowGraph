"""Headless FlowGraph workflow engine namespace."""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)

from .version import __version__

__all__ = ["__version__"]
