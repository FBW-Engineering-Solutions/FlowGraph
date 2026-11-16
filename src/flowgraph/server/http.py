"""Authenticated HTTP API; remote access requires an HTTPS reverse proxy."""

from __future__ import annotations

import hmac
import ipaddress
import json
import math
import secrets
import sys
from collections.abc import Sequence
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
        host: str = "127.0.0.1",
        public_url: str | None = None,
        token: str | None = None,
        max_request: int = 16 << 20,
        execution_timeout: float = 120,
        allowed_origins: tuple[str, ...] = (),
        verbose: bool = False,
        plugins: Sequence[str | Path] = (),
        allow_package_install: bool = False,
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
        address = ipaddress.IPv4Address(host)
        public = urlsplit(public_url) if public_url is not None else None
        if public is not None:
            if (
                public.scheme != "https"
                or not public.hostname
                or public.username is not None
                or public.password is not None
                or public.path not in ("", "/")
                or public.query
                or public.fragment
                or "\\" in public_url
                or any(char.isspace() for char in public_url)
            ):
                raise ValueError("Public URL must be an HTTPS origin without credentials or a path")
            # Validate the port before opening the listening socket.
            _ = public.port
        if not address.is_loopback and public is None:
            raise ValueError(
                "Non-loopback binding requires --public-url and an HTTPS reverse proxy"
            )
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
        from flowgraph.server.packages import PackageManager

        self.packages = PackageManager(self.workspace.root, enabled=allow_package_install)
        if allow_package_install:
            try:
                import uv  # noqa: F401 - validate explicit optional installer dependency
            except ImportError as error:
                raise ValueError("Package installation requires flowgraph[server] (uv).") from error
        self.token = token or secrets.token_hex(32)
        self.max_request = max_request
        self.verbose = verbose
        from flowgraph.application.node_registry import create_node_registry
        from flowgraph.application.plugins import load_plugin_groups, resolve_plugin_paths
        from flowgraph.application.workflow_web_catalog import workflow_web_catalog

        self.plugins = resolve_plugin_paths(plugins)
        groups = load_plugin_groups(self.plugins)
        create_node_registry(extra_groups=groups)
        self.catalog = workflow_web_catalog(extra_groups=groups)
        self.jobs = JobManager(
            self.workspace.root, timeout=execution_timeout, verbose=verbose, plugins=self.plugins
        )
        self.report("Server state: starting")
        super().__init__((host, port), ApiHandler)
        if public is not None:
            public_host = public.hostname
            if ":" in public_host:
                public_host = f"[{public_host}]"
            self.authority = (
                f"{public_host}:{public.port}" if public.port not in (None, 443) else public_host
            )
        else:
            self.authority = f"{host}:{self.server_port}"
        self.origin = (
            f"https://{self.authority}" if public is not None else f"http://{self.authority}"
        )
        self.report(f"Workspace: {str(self.workspace.root)!r}")
        self.report(f"Allowed editor origins: {sorted(self.allowed_origins)!r}")
        self.report(
            f"Limits: execution={execution_timeout:g}s, request={max_request} bytes, "
            f"result={self.jobs.max_result} bytes"
        )

    def report(self, message: str) -> None:
        """Emit opt-in diagnostics without request credentials or payloads."""
        if self.verbose:
            print(f"[flowgraph] {message}", file=sys.stderr, flush=True)

    def serve_forever(self, poll_interval: float = 0.5) -> None:
        self.report(f"Server state: ready/listening at {self.origin}")
        try:
            super().serve_forever(poll_interval)
        finally:
            self.report("Server state: shutting down")

    def server_close(self) -> None:
        self.jobs.close()
        super().server_close()
        self.report("Server state: stopped")

    def runtime(self) -> dict:
        import platform

        from flowgraph.application.workflow_io import WORKFLOW_FORMAT, WORKFLOW_FORMAT_VERSION

        versions = {"Python": platform.python_version()}
        for name in (
            "FlowGraph",
            "Muscat",
            "NumPy",
            "SciPy",
            "h5py",
            "meshio",
            "MeshLane",
            "pyimagej",
            "cosapp",
            "pyplaid",
        ):
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
        extras = self.packages.distributions()
        packages = sorted(
            set(packages)
            | {canonical.metadata["Name"].lower().replace("_", "-") for canonical in extras}
        )
        for item in extras:
            versions[item.metadata["Name"]] = item.version
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
                "advisoryExecutionTimeout": 1,
                "incrementalExecution": 1,
                "scopedExecution": 1,
                "installPackages": self.packages.info()["enabled"],
            },
            "directory": str(self.workspace.root),
            "packages": packages,
            "versions": versions,
            "packageInstallation": self.packages.info(),
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
        # Only fixed route labels are logged; paths and query values are untrusted
        # and can contain credentials, filenames, or control characters.
        path = self.path.split("?", 1)[0]
        routes = {
            "/api/v1/runtime",
            "/api/v1/catalog",
            "/api/v1/executions",
            "/api/v1/execution-sessions/dispose",
            "/api/v1/files",
            "/api/v1/files/demo",
            "/api/v1/files/content",
        }
        endpoint = path if path in routes else "<unknown endpoint>"
        if path.startswith("/api/v1/executions/"):
            endpoint = "/api/v1/executions/<id>"
            if path.endswith("/cancel"):
                endpoint += "/cancel"
        self.server.report(f"HTTP {self.command} {endpoint} -> {status}")
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
                self._reply(200, self.server.catalog)
            elif method == "POST" and path in {
                "/api/v1/packages/check",
                "/api/v1/packages/install",
            }:
                body = self._body(json_body=True)
                # Share the execution admission lock: never install into running workers.
                with self.server.jobs.lock:
                    if self.server.jobs.active is not None:
                        raise ApiError(
                            409, "Wait for workflow execution to finish before managing packages."
                        )
                    self.server.packages.require_enabled()
                    if path.endswith("/check"):
                        result = self.server.packages.check(body.get("name"))
                    else:
                        result = self.server.packages.install(body.get("token"))
                        for session_id in list(self.server.jobs.sessions):
                            self.server.jobs.dispose_session(session_id)
                self._reply(200, result)
            elif method == "POST" and path == "/api/v1/executions":
                body = self._body(json_body=True)
                workflow = body.get("workflow")
                if not isinstance(workflow, dict):
                    raise ApiError(400, "workflow must be a workflow JSON object")
                self._reply(
                    202,
                    self.server.jobs.submit(
                        workflow, body.get("options"), body.get("timeout_seconds")
                    ),
                )
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
