"""Workflow nodes for downloading remote files to the local temporary directory."""

import asyncio
import os
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import unquote, urlparse
from urllib.request import urlopen

from flowgraph.adapters.data_types import STRING, ParameterKind
from flowgraph.application.workflow_core import (
    NodeDefinition,
    ParameterDefinition,
    PortDefinition,
    PortDirection,
)

IS_PYODIDE = sys.platform == "emscripten" or "pyodide" in sys.modules


class RemoteFileDownloadError(RuntimeError):
    """Raised when a remote file cannot be downloaded to a temporary file."""


def _download_desktop_content(url: str) -> bytes:
    """Download URL content with CPython's blocking standard-library HTTP client."""
    try:
        with urlopen(url) as response:
            return response.read()
    except HTTPError as error:
        raise RemoteFileDownloadError(f"Failed to fetch {url}: HTTP {error.code}") from error
    except OSError as error:
        raise RemoteFileDownloadError(f"Failed to fetch {url}: {error}") from error


async def download_content(url: str) -> bytes:
    """Download URL content in desktop Python or Pyodide.

    Parameters
    ----------
    url:
        HTTP(S) URL to download.

    Returns
    -------
    bytes
        The complete response body.

    Raises
    ------
    RemoteFileDownloadError
        If the request cannot be completed successfully.
    """
    if IS_PYODIDE:
        from pyodide.http import pyfetch

        response = await pyfetch(url)
        if not response.ok:
            raise RemoteFileDownloadError(f"Failed to fetch {url}: HTTP {response.status}")
        return await response.bytes()

    return await asyncio.to_thread(_download_desktop_content, url)


def _url_suffix(url: str) -> str:
    """Return a safe filename suffix inferred from a URL path, if one exists."""
    suffix = Path(unquote(urlparse(url).path)).suffix
    return suffix if suffix and len(suffix) <= 20 else ".bin"


def _download_url(_inputs: Mapping[str, Any], parameters: Mapping[str, Any]) -> Mapping[str, Any]:
    """Download the configured URL to a persistent file in the system temporary directory."""
    url = parameters.get("url", "")
    if not isinstance(url, str) or not url.strip():
        raise ValueError("The download URL must be non-empty text")
    if urlparse(url).scheme not in {"http", "https"}:
        raise ValueError("The download URL must use HTTP or HTTPS")
    descriptor, filename = tempfile.mkstemp(prefix="flowgraph-download-", suffix=_url_suffix(url))
    destination = Path(filename)
    try:
        if IS_PYODIDE:
            from pyodide.ffi import can_run_sync, run_sync

            if not can_run_sync():
                raise RemoteFileDownloadError(
                    "Downloading URLs in Pyodide requires JavaScript Promise Integration (JSPI)"
                )
            content = run_sync(download_content(url))
        else:
            content = _download_desktop_content(url)
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return {"path": str(destination)}


DOWNLOAD_URL = NodeDefinition(
    id="download-url",
    icon="mdi-cloud-upload-outline",
    label="Download URL",
    description="Downloads an HTTP(S) URL to a temporary file and outputs its local path.",
    ports=(PortDefinition("path", PortDirection.OUTPUT, STRING, "File path"),),
    executor=_download_url,
    parameters=(
        ParameterDefinition("url", ParameterKind.TEXT, "URL", "", "https://example.com/file.ext"),
    ),
)

AVAILABLE_NODES = (DOWNLOAD_URL,)

__all__ = ["AVAILABLE_NODES", "DOWNLOAD_URL", "RemoteFileDownloadError", "download_content"]
