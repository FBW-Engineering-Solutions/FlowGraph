"""Prototype authenticated HTTP API, restricted to IPv4 loopback."""

from __future__ import annotations

import hmac
import json
import math
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import metadata
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from flowgraph.server.jobs import JobManager
from flowgraph.server.workspace import Workspace


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


class LocalServer(ThreadingHTTPServer):
    """Authenticated API only; GUI assets are owned and served by clients."""

    daemon_threads = False

    def __init__(
        self,
        workspace: Path,
        *,
        port: int = 8765,
        token: str | None = None,
        max_request: int = 16 << 20,
        execution_timeout: float = 120,
        allowed_origins: tuple[str, ...] = (),
    ):
        if (
            not 0 <= port <= 65535
            or max_request <= 0
            or not math.isfinite(execution_timeout)
            or execution_timeout <= 0
        ):
            raise ValueError("Invalid port, request limit, or execution timeout")
        if token is not None and (len(token) < 32 or not token.isascii() or not token.isalnum()):
            raise ValueError("Token must contain at least 32 ASCII letters/digits")
        for origin in allowed_origins:
            parsed = urlsplit(origin)
            if (
                not (
                    parsed.scheme == "https"
                    or (
                        parsed.scheme == "http"
                        and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
                    )
                )
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or origin != f"{parsed.scheme}://{parsed.netloc}"
                or any(char.isspace() for char in origin)
            ):
                raise ValueError(
                    "Allowed origins must be HTTPS (or HTTP loopback for development), "
                    "without paths or credentials"
                )
        self.allowed_origins = frozenset(allowed_origins)
        self.workspace = Workspace(workspace)
        self.token = token or secrets.token_hex(32)
        self.max_request = max_request
        self.jobs = JobManager(self.workspace.root, timeout=execution_timeout)
        super().__init__(("127.0.0.1", port), ApiHandler)
        self.authority = f"127.0.0.1:{self.server_port}"
        self.origin = f"http://{self.authority}"

    def server_close(self) -> None:
        self.jobs.close()
        super().server_close()

    def runtime(self) -> dict:
        import platform

        from flowgraph.application.workflow_io import WORKFLOW_FORMAT, WORKFLOW_FORMAT_VERSION

        versions = {"Python": platform.python_version()}
        for name in ("FlowGraph", "Muscat", "NumPy", "SciPy", "h5py", "meshio", "MeshLane"):
            try:
                versions[name] = metadata.version(name)
            except metadata.PackageNotFoundError:
                versions[name] = None
        packages = sorted(
            {
                item.metadata["Name"].lower().replace("_", "-")
                for item in metadata.distributions()
                if item.metadata["Name"]
            }
        )
        return {
            "protocol": "flowgraph-local-server",
            "version": 1,
            "kind": "native",
            "available": True,
            "status": "Native Python backend ready.",
            "workflow_format": WORKFLOW_FORMAT,
            "workflow_format_version": WORKFLOW_FORMAT_VERSION,
            "capabilities": {
                "mountDirectory": False,
                "cancelExecution": True,
                "incrementalExecution": 1,
                "scopedExecution": 1,
            },
            "directory": str(self.workspace.root),
            "packages": packages,
            "versions": versions,
            "limits": {
                "request_bytes": self.max_request,
                "result_bytes": self.jobs.max_result,
                "execution_seconds": self.jobs.timeout,
                "retained_jobs": 32,
            },
        }


class ApiHandler(BaseHTTPRequestHandler):
    server: LocalServer
    server_version = "FlowGraphPrototype/1"
    sys_version = ""

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, _format: str, *_args: object) -> None:
        """Do not log request URLs, tokens, workspace names, or workflow data."""

    def _reply(self, status: int, value, *, binary: bool = False) -> None:
        body = value if binary else json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header(
            "Content-Type",
            "application/octet-stream" if binary else "application/json; charset=utf-8",
        )
        self.send_header("Content-Length", str(len(body)))
        origins = self.headers.get_all("Origin") or []
        if len(origins) == 1 and origins[0] in self.server.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origins[0])
            self.send_header("Vary", "Origin")
            if self.command == "OPTIONS" and status == 200:
                self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                if self.headers.get("Access-Control-Request-Private-Network") == "true":
                    self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _check_origin(self) -> None:
        if self.headers.get_all("Host") != [self.server.authority]:
            raise ApiError(403, "Invalid Host")
        origins = self.headers.get_all("Origin")
        external = (
            origins is not None and len(origins) == 1 and origins[0] in self.server.allowed_origins
        )
        if origins is not None and origins != [self.server.origin] and not external:
            raise ApiError(403, "Cross-origin requests are not allowed")
        if not external and self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
            raise ApiError(403, "Cross-site requests are not allowed")

    def do_OPTIONS(self) -> None:
        try:
            self._check_origin()
            origins = self.headers.get_all("Origin") or []
            if len(origins) != 1 or origins[0] not in self.server.allowed_origins:
                raise ApiError(403, "Origin is not enabled for browser connections")
            if not urlsplit(self.path).path.startswith("/api/v1/"):
                raise ApiError(404, "Unknown API endpoint")
            if self.headers.get_all("Access-Control-Request-Method") not in (
                ["GET"],
                ["POST"],
                ["PUT"],
                ["DELETE"],
            ):
                raise ApiError(403, "Unsupported preflight method")
            requested = ",".join(self.headers.get_all("Access-Control-Request-Headers") or [])
            if any(
                name.strip().lower() not in {"authorization", "content-type"}
                for name in requested.split(",")
                if name.strip()
            ):
                raise ApiError(403, "Unsupported preflight headers")
            self._reply(200, {})
        except ApiError as exc:
            self._reply(exc.status, {"error": str(exc)})

    def _authorize(self) -> None:
        self._check_origin()
        authorization = self.headers.get_all("Authorization") or []
        expected = f"Bearer {self.server.token}"
        if len(authorization) != 1 or not hmac.compare_digest(authorization[0], expected):
            raise ApiError(401, "A valid bearer token is required")

    def _body(self, *, json_body: bool = False):
        if self.headers.get("Transfer-Encoding") is not None:
            raise ApiError(400, "Transfer-Encoding is not supported")
        lengths = self.headers.get_all("Content-Length") or []
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
            raise ApiError(411, "A single Content-Length is required")
        length = int(lengths[0])
        if length > self.server.max_request:
            raise ApiError(413, "Request exceeds the server size limit")
        data = self.rfile.read(length)
        if len(data) != length:
            raise ApiError(400, "Incomplete request body")
        if not json_body:
            return data
        if self.headers.get_content_type() != "application/json":
            raise ApiError(415, "Content-Type must be application/json")
        try:
            value = json.loads(data)
        except (ValueError, UnicodeError, RecursionError) as error:
            raise ApiError(400, "Invalid JSON body") from error
        if not isinstance(value, dict):
            raise ApiError(400, "JSON body must be an object")
        return value

    def _handle(self) -> None:
        try:
            self._check_origin()
            parsed = urlsplit(self.path)
            if parsed.scheme or parsed.netloc or parsed.fragment:
                raise ApiError(400, "An origin-relative API path is required")
            path = parsed.path
            method = self.command
            if not path.startswith("/api/"):
                self._check_origin()
                raise ApiError(404, "Unknown API endpoint")
            self._authorize()
            if method == "GET" and path == "/api/v1/runtime":
                self._reply(200, self.server.runtime())
            elif method == "GET" and path == "/api/v1/catalog":
                from flowgraph.application.workflow_web_catalog import workflow_web_catalog

                self._reply(200, workflow_web_catalog())
            elif method == "POST" and path == "/api/v1/executions":
                body = self._body(json_body=True)
                workflow = body.get("workflow")
                if not isinstance(workflow, dict):
                    raise ApiError(400, "workflow must be a workflow JSON object")
                self._reply(202, self.server.jobs.submit(workflow, body.get("options")))
            elif method == "POST" and path == "/api/v1/execution-sessions/dispose":
                body = self._body(json_body=True)
                session_id = body.get("session_id")
                if not isinstance(session_id, str):
                    raise ApiError(400, "session_id must be text")
                self.server.jobs.dispose_session(session_id)
                self._reply(200, {"status": "ok"})
            elif path.startswith("/api/v1/executions/"):
                parts = path.removeprefix("/api/v1/executions/").split("/")
                if method == "GET" and len(parts) == 1:
                    self._reply(200, self.server.jobs.get(parts[0]))
                elif method == "POST" and len(parts) == 2 and parts[1] == "cancel":
                    self._body()
                    self._reply(200, self.server.jobs.cancel(parts[0]))
                else:
                    raise ApiError(404, "Unknown execution endpoint")
            elif path == "/api/v1/files" and method == "GET":
                self._reply(200, self.server.workspace.listing())
            elif path == "/api/v1/files/demo" and method == "POST":
                self._body()
                self._reply(200, self.server.workspace.copy_demos())
            elif path == "/api/v1/files/content" and method in {"GET", "PUT", "DELETE"}:
                names = parse_qs(parsed.query).get("path", [])
                if len(names) != 1:
                    raise ApiError(400, "Exactly one path query parameter is required")
                if method == "GET":
                    self._reply(
                        200,
                        self.server.workspace.read(names[0], self.server.max_request),
                        binary=True,
                    )
                elif method == "PUT":
                    self._reply(200, self.server.workspace.write(names[0], self._body()))
                else:
                    self._reply(200, self.server.workspace.delete(names[0]))
            else:
                raise ApiError(404, "Unknown API endpoint")
        except ApiError as error:
            self._reply(error.status, {"error": str(error)})
        except (KeyError, FileNotFoundError):
            self._reply(404, {"error": "Job or file not found"})
        except FileExistsError as error:
            self._reply(409, {"error": str(error)})
        except RuntimeError as error:
            self._reply(409, {"error": str(error)})
        except (ValueError, IsADirectoryError, NotADirectoryError) as error:
            self._reply(400, {"error": str(error)})
        except PermissionError:
            self._reply(403, {"error": "Filesystem permission denied"})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except Exception:  # noqa: BLE001 - do not expose internal errors to HTTP clients
            self._reply(500, {"error": "Internal server error"})

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_DELETE = _handle
