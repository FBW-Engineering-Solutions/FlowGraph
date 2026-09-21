import asyncio
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType

import pytest

from flowgraph.adapters import remote_files
from flowgraph.adapters.remote_files import DOWNLOAD_URL, RemoteFileDownloadError


@pytest.fixture
def file_server() -> Iterator[str]:
    """Serve deterministic binary content from a local HTTP endpoint."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/sample.data":
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", "5")
                self.end_headers()
                self.wfile.write(b"hello")
                return
            self.send_error(404)

        def log_message(self, _format: str, *_args: object) -> None:
            """Suppress expected local test-server log messages."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_download_url_writes_content_to_a_temporary_file(file_server: str) -> None:
    output = DOWNLOAD_URL.executor({}, {"url": f"{file_server}/sample.data"})
    path = Path(output["path"])

    try:
        assert path.is_file()
        assert path.suffix == ".data"
        assert path.read_bytes() == b"hello"
    finally:
        path.unlink(missing_ok=True)


def test_download_url_executes_when_an_event_loop_is_running(file_server: str) -> None:
    """Ensure the synchronous node executor does not create a nested event loop."""

    async def download() -> Path:
        output = DOWNLOAD_URL.executor({}, {"url": f"{file_server}/sample.data"})
        return Path(output["path"])

    path = asyncio.run(download())
    try:
        assert path.read_bytes() == b"hello"
    finally:
        path.unlink(missing_ok=True)


def test_download_url_uses_pyodide_promise_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    async def download_content(_url: str) -> bytes:
        return b"browser content"

    def run_sync(awaitable: object) -> bytes:
        return asyncio.run(awaitable)  # type: ignore[arg-type]

    pyodide = ModuleType("pyodide")
    pyodide_ffi = ModuleType("pyodide.ffi")
    pyodide_ffi.can_run_sync = lambda: True  # type: ignore[attr-defined]
    pyodide_ffi.run_sync = run_sync  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pyodide", pyodide)
    monkeypatch.setitem(sys.modules, "pyodide.ffi", pyodide_ffi)
    monkeypatch.setattr(remote_files, "IS_PYODIDE", True)
    monkeypatch.setattr(remote_files, "download_content", download_content)

    output = DOWNLOAD_URL.executor({}, {"url": "https://example.com/data.bin"})
    path = Path(output["path"])
    try:
        assert path.suffix == ".bin"
        assert path.read_bytes() == b"browser content"
    finally:
        path.unlink(missing_ok=True)


def test_download_url_reports_when_pyodide_does_not_support_jspi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pyodide = ModuleType("pyodide")
    pyodide_ffi = ModuleType("pyodide.ffi")
    pyodide_ffi.can_run_sync = lambda: False  # type: ignore[attr-defined]
    pyodide_ffi.run_sync = lambda _awaitable: b""  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pyodide", pyodide)
    monkeypatch.setitem(sys.modules, "pyodide.ffi", pyodide_ffi)
    monkeypatch.setattr(remote_files, "IS_PYODIDE", True)

    with pytest.raises(RemoteFileDownloadError, match="JavaScript Promise Integration"):
        DOWNLOAD_URL.executor({}, {"url": "https://example.com/data.bin"})


def test_download_url_removes_reserved_file_when_pyodide_request_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[Path] = []

    async def download_content(_url: str) -> bytes:
        raise RemoteFileDownloadError("Failed to fetch https://example.com/missing.data: HTTP 404")

    def run_sync(awaitable: object) -> bytes:
        return asyncio.run(awaitable)  # type: ignore[arg-type]

    def mkstemp(*args: object, **kwargs: object) -> tuple[int, str]:
        descriptor, filename = original_mkstemp(*args, **kwargs)
        created.append(Path(filename))
        return descriptor, filename

    original_mkstemp = remote_files.tempfile.mkstemp
    pyodide = ModuleType("pyodide")
    pyodide_ffi = ModuleType("pyodide.ffi")
    pyodide_ffi.can_run_sync = lambda: True  # type: ignore[attr-defined]
    pyodide_ffi.run_sync = run_sync  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pyodide", pyodide)
    monkeypatch.setitem(sys.modules, "pyodide.ffi", pyodide_ffi)
    monkeypatch.setattr(remote_files, "IS_PYODIDE", True)
    monkeypatch.setattr(remote_files, "download_content", download_content)
    monkeypatch.setattr(remote_files.tempfile, "mkstemp", mkstemp)

    with pytest.raises(RemoteFileDownloadError, match="HTTP 404"):
        DOWNLOAD_URL.executor({}, {"url": "https://example.com/missing.data"})

    assert len(created) == 1
    assert not created[0].exists()


def test_download_url_removes_reserved_file_when_request_fails(
    file_server: str, monkeypatch
) -> None:
    created: list[Path] = []

    def mkstemp(*_args: object, **_kwargs: object) -> tuple[int, str]:
        descriptor, filename = original_mkstemp(*_args, **_kwargs)
        created.append(Path(filename))
        return descriptor, filename

    original_mkstemp = remote_files.tempfile.mkstemp
    monkeypatch.setattr(remote_files.tempfile, "mkstemp", mkstemp)

    with pytest.raises(RemoteFileDownloadError, match="HTTP 404"):
        DOWNLOAD_URL.executor({}, {"url": f"{file_server}/missing.data"})

    assert len(created) == 1
    assert not created[0].exists()


@pytest.mark.parametrize("url", ["", "ftp://example.com/file.txt", "file:///tmp/file.txt"])
def test_download_url_rejects_invalid_urls(url: str) -> None:
    with pytest.raises(ValueError):
        DOWNLOAD_URL.executor({}, {"url": url})
