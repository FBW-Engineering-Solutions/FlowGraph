"""Persistent ParaView Live gateway, runnable directly with ParaView's pvpython.

The gateway needs only ParaView's bundled libraries, not a FlowGraph installation.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import math
import queue
import signal
import socket
import socketserver
import struct
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

LOG = logging.getLogger("flowgraph.paraview_gateway")
MAX_PAYLOAD = 256 * 1024 * 1024
MAX_METADATA = 16 * 1024
HEADER = struct.Struct("!IQ")
KINDS = {"mesh": "UnstructuredGrid", "table": "Table", "image": "ImageData"}
HTTP_PATH = "/api/v1/dataset"
TRANSACTION_TTL = 60.0


def to_vtk(kind: str, value: Any) -> Any:
    """Project FlowGraph values without mutating the source."""
    import numpy as np
    from vtkmodules.util.numpy_support import numpy_to_vtk
    from vtkmodules.vtkCommonCore import vtkStringArray
    from vtkmodules.vtkCommonDataModel import vtkImageData, vtkTable

    if kind == "mesh":
        from vtkmodules.vtkFiltersCore import vtkAppendFilter

        projection = value.to_vtk_unstructured_grid()
        if projection.IsA("vtkUnstructuredGrid"):
            return projection
        converter = vtkAppendFilter()
        converter.AddInputData(projection)
        converter.Update()
        result = converter.GetOutput()
        result._projection_owner = projection
        return result
    if kind == "table":
        table = vtkTable()
        table._array_owners = []
        lengths = set()
        for name, column in value.items():
            if not isinstance(name, str) or not name:
                raise ValueError("Table column names must be nonempty strings")
            array = np.asarray(column)
            if array.ndim not in (1, 2) or (array.ndim == 2 and array.shape[1] == 0):
                raise ValueError(f"Table column {name!r} must be a scalar or vector column")
            lengths.add(len(array))
            if array.dtype.kind in "biuf":
                if array.dtype.kind == "b":
                    array = array.astype(np.uint8)
                vtk_array = numpy_to_vtk(np.ascontiguousarray(array), deep=False)
            elif array.ndim == 1 and all(isinstance(item, str) for item in column):
                vtk_array = vtkStringArray()
                for item in column:
                    vtk_array.InsertNextValue(item)
            else:
                raise ValueError(f"Table column {name!r} must contain numbers or strings")
            vtk_array.SetName(name)
            table.AddColumn(vtk_array)
            table._array_owners.append(vtk_array)
        if len(lengths) > 1:
            raise ValueError("Table columns must have equal row counts")
        return table
    if kind == "image":
        if value.mode == "P":
            value = value.convert("RGBA" if "transparency" in value.info else "RGB")
        elif value.mode == "1":
            value = value.convert("L")
        elif value.mode not in {"L", "LA", "RGB", "RGBA", "I", "F", "I;16"}:
            value = value.convert("RGB")
        pixels = np.asarray(value)
        height, width = pixels.shape[:2]
        if width == 0 or height == 0:
            raise ValueError(
                "Cannot send an empty image to ParaView (width and height must be positive)"
            )
        channels = 1 if pixels.ndim == 2 else pixels.shape[2]
        # VTK's bottom-left origin differs from Pillow's top-left origin.
        pixels = np.ascontiguousarray(pixels[::-1]).reshape(-1, channels)
        scalars = numpy_to_vtk(pixels, deep=False)
        scalars.SetName("pixels")
        image = vtkImageData()
        image.SetDimensions(width, height, 1)
        image.GetPointData().SetScalars(scalars)
        image._array_owners = [scalars]
        return image
    raise ValueError(f"Unsupported dataset kind: {kind!r}")


def serialize_dataset(kind: str, dataset: Any) -> bytes:
    """Serialize VTK XML with inline base64 arrays, without shared files."""
    from vtkmodules import vtkIOXML

    if kind not in KINDS or not dataset.IsA("vtk" + KINDS[kind]):
        raise ValueError(f"Dataset does not match kind {kind!r}")
    if kind == "image" and sys.platform == "emscripten":
        return _serialize_browser_image(dataset)
    writer = getattr(vtkIOXML, "vtkXML" + KINDS[kind] + "Writer")()
    writer.SetInputData(dataset)
    writer.SetDataModeToBinary()
    writer.WriteToOutputStringOn()
    if writer.Write() != 1 or writer.GetErrorCode():
        raise ValueError("Could not serialize VTK dataset")
    output = writer.GetOutputString()
    return output.encode("utf-8") if isinstance(output, str) else output


def _serialize_browser_image(dataset: Any) -> bytes:
    """Write inline VTI pixels without the WASM writer's broken extent pipeline."""
    from xml.etree.ElementTree import Element, SubElement, tostring

    from vtkmodules.util.numpy_support import vtk_to_numpy

    scalars = dataset.GetPointData().GetScalars()
    if scalars is None or dataset.GetNumberOfPoints() == 0:
        raise ValueError("Cannot serialize an image without pixels")
    if scalars.GetNumberOfTuples() != dataset.GetNumberOfPoints():
        raise ValueError("Image pixel count does not match its extent")
    pixels = vtk_to_numpy(scalars)
    dtype = pixels.dtype.newbyteorder("<")
    vtk_type = {"u": "UInt", "i": "Int", "f": "Float"}.get(dtype.kind)
    if vtk_type is None:
        raise ValueError(f"Unsupported image pixel dtype: {dtype}")
    byte_count = pixels.nbytes
    if 4 * ((byte_count + 4 + 2) // 3) + 4096 > MAX_PAYLOAD:
        raise ValueError("Gateway image exceeds the size limit")
    extent = " ".join(map(str, dataset.GetExtent()))
    root = Element(
        "VTKFile", type="ImageData", version="0.1", byte_order="LittleEndian", header_type="UInt32"
    )
    image = SubElement(
        root,
        "ImageData",
        WholeExtent=extent,
        Origin=" ".join(map(str, dataset.GetOrigin())),
        Spacing=" ".join(map(str, dataset.GetSpacing())),
        Direction=" ".join(
            str(dataset.GetDirectionMatrix().GetElement(i, j)) for i in range(3) for j in range(3)
        ),
    )
    piece = SubElement(image, "Piece", Extent=extent)
    points = SubElement(piece, "PointData", Scalars="pixels")
    array = SubElement(
        points,
        "DataArray",
        type=f"{vtk_type}{dtype.itemsize * 8}",
        Name="pixels",
        NumberOfComponents=str(scalars.GetNumberOfComponents()),
        format="binary",
    )
    raw = pixels.astype(dtype, copy=False).tobytes(order="C")
    array.text = base64.b64encode(struct.pack("<I", byte_count) + raw).decode("ascii")
    SubElement(piece, "CellData")
    return tostring(root, encoding="utf-8", xml_declaration=True)


def deserialize_dataset(kind: str, payload: bytes) -> Any:
    """Read the declared XML type and surface parsing errors."""
    from vtkmodules import vtkIOXML

    if kind not in KINDS:
        raise ValueError(f"Unsupported dataset kind: {kind!r}")
    reader = getattr(vtkIOXML, "vtkXML" + KINDS[kind] + "Reader")()
    errors = []
    reader.AddObserver("ErrorEvent", lambda *_args: errors.append(True))
    reader.ReadFromInputStringOn()
    reader.SetInputString(payload)
    reader.Update()
    if errors or reader.GetErrorCode():
        raise ValueError("Invalid VTK XML payload")
    return reader.GetOutput()


def _receive_exact(sock: socket.socket, size: int) -> bytes:
    data = bytearray(size)
    view = memoryview(data)
    offset = 0
    while offset < size:
        count = sock.recv_into(view[offset:])
        if not count:
            raise ValueError("Truncated gateway message")
        offset += count
    return bytes(data)


def _write_frame(sock: socket.socket, metadata: dict, payload: bytes = b"") -> None:
    encoded = json.dumps(metadata, ensure_ascii=True).encode("utf-8")
    if len(encoded) > MAX_METADATA or len(payload) > MAX_PAYLOAD:
        raise ValueError(
            f"Gateway message exceeds the size limit: metadata={len(encoded)} bytes "
            f"(maximum {MAX_METADATA}), payload={len(payload)} bytes (maximum {MAX_PAYLOAD})"
        )
    sock.sendall(HEADER.pack(len(encoded), len(payload)))
    sock.sendall(encoded)
    if payload:
        sock.sendall(payload)


def _read_frame(sock: socket.socket) -> tuple[dict, bytes]:
    header = _receive_exact(sock, HEADER.size)
    if header.startswith((b"GET ", b"POST ", b"OPTIONS ", b"HEAD ", b"PUT ", b"CONNECT ")):
        raise ValueError(
            "HTTP/WebSocket request received on the FlowGraph binary TCP port. "
            "Use the native Python Send to ParaView node on port 33333; "
            "browser fetch/WebSocket clients cannot use this raw TCP service. "
            "In ParaView use Catalyst > Connect on port 22222, not Connect to Server."
        )
    if header.lstrip().startswith((b"{", b"[")):
        raise ValueError(
            "Unframed JSON received; this is not the current FlowGraph bridge protocol. "
            "Restart the workflow Python process to reload the updated bridge "
            "and remove old socket/JSON test code."
        )
    if header.startswith(b"\x16\x03"):
        raise ValueError("TLS received on the plaintext FlowGraph TCP port (33333)")
    metadata_size, payload_size = HEADER.unpack(header)
    if not 0 < metadata_size <= MAX_METADATA or payload_size > MAX_PAYLOAD:
        raise ValueError(
            "Invalid gateway header or message exceeds the size limit: "
            f"metadata={metadata_size} bytes (allowed 1..{MAX_METADATA}), "
            f"payload={payload_size} bytes (maximum {MAX_PAYLOAD}), "
            f"header={header.hex()}. Check both processes use the current bridge protocol; "
            "FlowGraph sends binary TCP to 33333, ParaView listens for Catalyst on 22222."
        )
    metadata = json.loads(_receive_exact(sock, metadata_size))
    if not isinstance(metadata, dict):
        raise TypeError("Gateway metadata must be an object")
    return metadata, _receive_exact(sock, payload_size)


def send_dataset(
    node_id: str,
    kind: str,
    dataset: Any,
    *,
    host: str = "127.0.0.1",
    port: int = 33333,
    timeout: float = 10.0,
    input_name: str | None = None,
    transaction_id: str | None = None,
) -> None:
    """Send a dataset and wait for acknowledgement of gateway acceptance."""
    if not isinstance(node_id, str) or not node_id:
        raise ValueError("node_id must be a nonempty string")
    if input_name is not None and (not isinstance(input_name, str) or not input_name):
        raise ValueError("input_name must be a nonempty string")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("port must be an integer between 1 and 65535")
    payload = serialize_dataset(kind, dataset)
    metadata = {"version": 1, "node_id": node_id, "kind": kind}
    if input_name is not None:
        metadata["input_name"] = input_name
    if transaction_id is not None:
        metadata["transaction_id"] = transaction_id
    _send_message(host, port, timeout, metadata, payload)


def _send_message(host: str, port: int, timeout: float, metadata: dict, payload: bytes) -> None:
    """Carry dataset and transaction messages over the same acknowledged transport."""
    if sys.platform == "emscripten":
        _send_browser_dataset(host, port, timeout, metadata, payload)
        return
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            _write_frame(sock, metadata, payload)
            reply, _ = _read_frame(sock)
            if reply.get("ok") is not True:
                raise ValueError(reply.get("error", "Gateway rejected the dataset"))
    except (OSError, ValueError, TypeError) as error:
        raise RuntimeError(f"ParaView gateway {host}:{port}: {error}") from error


@contextmanager
def data_transaction(node_id: str, *, host="127.0.0.1", port=33333, timeout=10.0):
    """Atomically replace one node's retained inputs; preserve old data on failure."""
    if not isinstance(node_id, str) or not node_id:
        raise ValueError("node_id must be a nonempty string")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("port must be an integer between 1 and 65535")
    transaction_id = uuid.uuid4().hex
    metadata = {"version": 1, "node_id": node_id, "transaction_id": transaction_id}
    _send_message(host, port, timeout, {**metadata, "operation": "begin"}, b"")
    try:
        yield transaction_id
        _send_message(host, port, timeout, {**metadata, "operation": "commit"}, b"")
    except BaseException:
        try:
            _send_message(host, port, timeout, {**metadata, "operation": "abort"}, b"")
        except Exception:  # noqa: BLE001 -- preserve the original failure
            LOG.warning("Could not abort transaction %s; it will expire", transaction_id)
        raise


def _send_browser_dataset(
    host: str, port: int, timeout: float, metadata: dict, payload: bytes
) -> None:
    """Use synchronous HTTP inside the existing Pyodide Web Worker only."""
    from js import XMLHttpRequest, globalThis
    from pyodide.ffi import JsException, to_js

    if hasattr(globalThis, "document"):
        raise RuntimeError("Send to ParaView requires Pyodide execution in a Web Worker")
    if any(character in host for character in "/?#@"):
        raise ValueError("Gateway host must be a hostname or IP, not a URL")
    encoded = json.dumps(metadata, ensure_ascii=True).encode("utf-8")
    if len(encoded) > MAX_METADATA or len(payload) > MAX_PAYLOAD:
        raise ValueError("Gateway message exceeds the size limit")
    # Exactly the native protocol, carried as one HTTP body instead of a socket.
    body = HEADER.pack(len(encoded), len(payload)) + encoded + payload
    authority = f"[{host}]" if ":" in host and not host.startswith("[") else host
    url = f"http://{authority}:{port}{HTTP_PATH}"
    request = XMLHttpRequest.new()
    try:
        request.open("POST", url, False)
        request.timeout = int(timeout * 1000)
        request.setRequestHeader("Content-Type", "application/octet-stream")
        request.send(to_js(memoryview(body)))
        if request.status != 200:
            raise RuntimeError(f"HTTP {request.status}: {request.responseText}")
        reply = json.loads(str(request.responseText))
        if reply.get("ok") is not True:
            raise RuntimeError(reply.get("error", "Gateway rejected the dataset"))
    except JsException as error:
        raise RuntimeError(
            f"ParaView HTTP gateway {url}: {error}. Check the gateway is running, "
            "--allow-origin matches the editor origin, and browser local-network permission."
        ) from error


@dataclass
class Update:
    """Transfer ownership from the socket thread to the VTK main thread."""

    metadata: dict
    payload: bytes
    done: threading.Event = field(default_factory=threading.Event)
    error: str | None = None


class GatewayServer(socketserver.TCPServer):
    """Sequential bounded receiver; VTK work stays on the main thread."""

    allow_reuse_address = True

    def __init__(
        self, address: tuple[str, int], updates: queue.Queue, allowed_origins: tuple[str, ...] = ()
    ):
        if any("\r" in origin or "\n" in origin for origin in allowed_origins):
            raise ValueError("Allowed origins must not contain CR or LF")
        self.updates = updates
        self.allowed_origins = allowed_origins
        super().__init__(address, _Handler)

    def accept_update(self, metadata: dict, payload: bytes) -> None:
        """Share validation/acknowledgement between HTTP and native TCP clients."""
        operation = metadata.get("operation", "dataset")
        if (
            metadata.get("version") != 1
            or not isinstance(metadata.get("node_id"), str)
            or not metadata["node_id"]
        ):
            raise ValueError("Expected version 1 and nonempty node_id")
        transaction_id = metadata.get("transaction_id")
        if transaction_id is not None and (
            not isinstance(transaction_id, str) or not 0 < len(transaction_id) <= 128
        ):
            raise ValueError("Invalid transaction_id")
        if operation == "dataset":
            kind = metadata.get("kind")
            if (
                not isinstance(kind, str)
                or kind not in KINDS
                or not isinstance(metadata.get("input_name", kind), str)
                or not metadata.get("input_name", kind)
                or not payload
            ):
                raise ValueError("Expected kind and VTK XML payload with nonempty input_name")
        elif operation not in {"begin", "commit", "abort"} or not transaction_id or payload:
            raise ValueError("Expected begin, commit or abort with transaction_id and no payload")
        update = Update(metadata, payload)
        self.updates.put(update, timeout=10)
        if not update.done.wait(10):
            raise ValueError("Gateway busy; acceptance unknown (retry replaces the same source)")
        if update.error:
            raise ValueError(update.error)


class _HTTPHandler(BaseHTTPRequestHandler):
    """Opt-in, exact-origin HTTP uploads on the native receiver's port."""

    def log_message(self, format: str, *args: Any) -> None:
        LOG.info("HTTP %s: %s", self.client_address[0], format % args)

    def do_GET(self) -> None:
        if self.headers.get("Upgrade", "").lower() == "websocket":
            message = (
                "WebSocket client detected (likely an old WASM worker using socket emulation). "
                "Rebuild the web runtime with make build, close/reload the editor tab, "
                "and run again. The current WASM node uses POST /api/v1/dataset, not WebSocket."
            )
            LOG.warning("HTTP %s: %s", self.client_address[0], message)
            self._reply(426, message)
        elif self.path in {"/", "/health"}:
            # Reachability only: never expose datasets or claim Catalyst is connected.
            body = json.dumps(
                {
                    "service": "flowgraph-paraview-gateway",
                    "status": "listening",
                    "upload": f"POST {HTTP_PATH}",
                    "note": "GET does not upload data or establish a Catalyst connection.",
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
        else:
            self._reply(
                404, f"Use POST {HTTP_PATH} to send data, or GET /health to check reachability"
            )

    def _reply(self, status: int, error: str | None = None) -> None:
        body = json.dumps({"ok": error is None, **({"error": error} if error else {})}).encode()
        self.send_response(status)
        request_origin = self.headers.get("Origin")
        for allowed_origin in self.server.allowed_origins:
            if request_origin == allowed_origin:
                # Emit trusted configuration, never the request header itself.
                self.send_header("Access-Control-Allow-Origin", allowed_origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Access-Control-Allow-Private-Network", "true")
                break
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        if self.headers.get("Origin") not in self.server.allowed_origins:
            self._reply(
                403, "Browser origin not allowed; restart gateway with --allow-origin ORIGIN"
            )
            return False
        if self.path != HTTP_PATH:
            self._reply(404, f"Use POST {HTTP_PATH}")
            return False
        return True

    def do_OPTIONS(self) -> None:
        if self._authorized():
            if self.headers.get("Access-Control-Request-Method") != "POST":
                self._reply(405, "Only POST is supported")
            else:
                self._reply(200)

    def do_POST(self) -> None:
        if not self._authorized():
            return
        try:
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("Transfer-Encoding is not supported")
            if self.headers.get("Content-Type") != "application/octet-stream":
                raise ValueError("Expected Content-Type application/octet-stream")
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1:
                raise ValueError("Expected one Content-Length")
            length = int(lengths[0])
            if not HEADER.size < length <= HEADER.size + MAX_METADATA + MAX_PAYLOAD:
                raise ValueError("HTTP body exceeds the size limit")
            header = self.rfile.read(HEADER.size)
            if len(header) != HEADER.size:
                raise ValueError("Truncated HTTP gateway header")
            metadata_size, payload_size = HEADER.unpack(header)
            if (
                not 0 < metadata_size <= MAX_METADATA
                or not 0 <= payload_size <= MAX_PAYLOAD
                or length != HEADER.size + metadata_size + payload_size
            ):
                raise ValueError("Invalid HTTP gateway lengths or message exceeds the size limit")
            encoded = self.rfile.read(metadata_size)
            metadata = json.loads(encoded)
            if not isinstance(metadata, dict):
                raise TypeError("Gateway metadata must be an object")
            payload = self.rfile.read(payload_size)
            if len(payload) != payload_size:
                raise ValueError("Truncated HTTP gateway payload")
            self.server.accept_update(metadata, payload)
        except (OSError, ValueError, TypeError, queue.Full) as error:
            self._reply(400, str(error)[:2000])
        else:
            self._reply(200)


class _Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.request.settimeout(10)
        try:
            first = self.request.recv(1, socket.MSG_PEEK)
            if first and first in b"GPOHCDT":
                _HTTPHandler(self.request, self.client_address, self.server)
                return
            metadata, payload = _read_frame(self.request)
            self.server.accept_update(metadata, payload)
            _write_frame(self.request, {"ok": True})
        except (OSError, ValueError, TypeError, queue.Full) as error:
            LOG.warning("Rejected update from %s:%s: %s", *self.client_address, error)
            try:
                _write_frame(self.request, {"ok": False, "error": str(error)[:2000]})
            except OSError:
                pass


class LiveGateway:
    """Publish named dataset blocks through a source registered before connection."""

    def __init__(self, host: str, port: int, max_sources: int = 128, live_interval: float = 1.0):
        from paraview import servermanager, simple
        from vtkmodules.vtkCommonDataModel import vtkMultiBlockDataSet

        self.simple = simple
        self.producers = {}
        self.transactions = {}
        # Catalyst publishes source proxies at connection time, not on upload.
        # Register a stable composite source before Initialize can connect.
        self.blocks = vtkMultiBlockDataSet()
        self.block_indices = {}
        self.output = simple.PVTrivialProducer(registrationName="FlowGraph outputs")
        self.output.GetClientSideObject().SetOutput(self.blocks)
        self.output.UpdatePipeline()
        self.max_sources = max_sources
        self.step = 0
        self.paraview_host = host
        self.paraview_port = port
        self.connected: bool | None = None
        self.live_interval = live_interval
        self.next_delivery = 0.0
        self.delivery_pending = True
        self.link = servermanager.vtkLiveInsituLink()
        self.link.SetHostname(host)
        self.link.SetInsituPort(port)
        self.manager = servermanager.ActiveConnection.Session.GetSessionProxyManager()

    def accept(self, update: Update) -> None:
        from vtkmodules.vtkCommonCore import vtkStringArray

        try:
            operation = update.metadata.get("operation", "dataset")
            self._expire_transactions()
            node_id = update.metadata["node_id"]
            transaction_id = update.metadata.get("transaction_id")
            transaction_key = (node_id, transaction_id)
            if operation == "begin":
                if any(key[0] == node_id for key in self.transactions):
                    raise ValueError("A transaction is already active for this node")
                if len(self.transactions) >= self.max_sources:
                    raise ValueError("Gateway transaction limit reached")
                self.transactions[transaction_key] = (time.monotonic(), {}, 0)
                return
            if operation == "abort":
                self.transactions.pop(transaction_key, None)
                return
            if operation == "commit":
                if transaction_key not in self.transactions:
                    raise ValueError("Unknown or expired transaction")
                _, staged, _ = self.transactions[transaction_key]
                retained = {
                    key: value for key, value in self.producers.items() if key[0] != node_id
                }
                if len(retained) + len(staged) > self.max_sources:
                    raise ValueError(f"Gateway source limit reached ({self.max_sources})")
                retained.update(staged)
                self.producers = retained
                self.transactions.pop(transaction_key)
                # Keep existing block positions. Removed slots become empty and
                # are reused for new identities instead of growing indefinitely.
                for key in list(self.block_indices):
                    if key not in retained:
                        index = self.block_indices.pop(key)
                        self.blocks.SetBlock(index, None)
                        self.blocks.GetMetaData(index).Clear()
                for key, dataset in staged.items():
                    self._set_block(key, dataset)
                self._publish_blocks()
                LOG.info("Committed %s: %s retained inputs", node_id, len(staged))
                return
            if transaction_id is not None and transaction_key not in self.transactions:
                raise ValueError("Unknown or expired transaction")
            if transaction_id is None and any(key[0] == node_id for key in self.transactions):
                raise ValueError("Node has an active transaction")
            node_id, kind = update.metadata["node_id"], update.metadata["kind"]
            input_name = update.metadata.get("input_name", kind)
            key = (node_id, input_name)
            if (
                transaction_id is None
                and key not in self.producers
                and len(self.producers) >= self.max_sources
            ):
                raise ValueError(f"Gateway source limit reached ({self.max_sources})")
            dataset = deserialize_dataset(kind, update.payload)
            if kind == "image":
                scalars = dataset.GetPointData().GetScalars()
                if (
                    dataset.GetNumberOfPoints() == 0
                    or scalars is None
                    or scalars.GetNumberOfTuples() != dataset.GetNumberOfPoints()
                ):
                    raise ValueError(
                        "Image upload has no pixels or an invalid pixel count: "
                        f"dimensions={dataset.GetDimensions()}, "
                        f"extent={dataset.GetExtent()}, points={dataset.GetNumberOfPoints()}"
                    )
            identity = vtkStringArray()
            identity.SetName("flowgraph_workflow_node_id")
            identity.InsertNextValue(node_id)
            dataset.GetFieldData().AddArray(identity)
            if transaction_id is not None:
                _, staged, size = self.transactions[transaction_key]
                if key in staged:
                    raise ValueError("Duplicate input in transaction")
                total_staged = sum(item[2] for item in self.transactions.values())
                if (
                    len(staged) >= self.max_sources
                    or total_staged + len(update.payload) > MAX_PAYLOAD
                ):
                    raise ValueError("Gateway staged transaction size/source limit reached")
                staged[key] = dataset
                self.transactions[transaction_key] = (
                    time.monotonic(),
                    staged,
                    size + len(update.payload),
                )
            else:
                self.producers[key] = dataset
                self._set_block(key, dataset)
                self._publish_blocks()
            if kind == "image":
                LOG.info(
                    "Image %s/%s: dimensions=%s, extent=%s, points=%s, cells=%s, "
                    "pixel tuples=%s, components=%s",
                    node_id,
                    input_name,
                    dataset.GetDimensions(),
                    dataset.GetExtent(),
                    dataset.GetNumberOfPoints(),
                    dataset.GetNumberOfCells(),
                    scalars.GetNumberOfTuples(),
                    scalars.GetNumberOfComponents(),
                )
            LOG.info(
                "Updated %s/%s (%s); extract 'FlowGraph outputs' in ParaView. "
                "The dataset is a named block, not a new live source.",
                node_id,
                input_name,
                dataset.GetClassName(),
            )
        except Exception as error:  # noqa: BLE001 -- isolate malformed updates from the service
            # A rejected member invalidates the entire transaction, even if a
            # client mistakenly attempts to commit after receiving the error.
            if update.metadata.get("transaction_id") and operation == "dataset":
                self.transactions.pop(transaction_key, None)
            update.error = str(error)
        finally:
            update.done.set()

    def _expire_transactions(self) -> None:
        if not hasattr(self, "transactions"):
            self.transactions = {}
        now = time.monotonic()
        for key, (updated, _, _) in list(self.transactions.items()):
            if now - updated >= TRANSACTION_TTL:
                self.transactions.pop(key)
                LOG.warning("Expired data transaction for %s", key[0])

    def _set_block(self, key, dataset) -> None:
        from vtkmodules.vtkCommonDataModel import vtkCompositeDataSet

        if key not in self.block_indices:
            occupied = set(self.block_indices.values())
            self.block_indices[key] = next(i for i in range(len(occupied) + 1) if i not in occupied)
        index = self.block_indices[key]
        self.blocks.SetBlock(index, dataset)
        self.blocks.GetMetaData(index).Set(vtkCompositeDataSet.NAME(), "/".join(key))

    def _publish_blocks(self) -> None:
        self.blocks.Modified()
        self.output.GetClientSideObject().SetOutput(self.blocks)
        self.output.GetClientSideObject().Modified()
        self.output.UpdatePipeline()
        self.delivery_pending = True

    def tick(self) -> None:
        """Poll controls while idle; deliver only new data or changed live state."""
        from vtkmodules.vtkCommonCore import vtkTimeStamp

        self._expire_transactions()
        connected = bool(self.link.Initialize(self.manager))
        if connected != self.connected:
            if connected:
                self.delivery_pending = True
                self.next_delivery = 0.0
                LOG.info(
                    "Connected to ParaView Catalyst Live at %s:%s. "
                    "Extract 'FlowGraph outputs' in the Catalyst pipeline and enable visibility "
                    "to display data.",
                    self.paraview_host,
                    self.paraview_port,
                )
            elif self.connected:
                LOG.warning(
                    "Disconnected from ParaView Catalyst Live at %s:%s; retrying. "
                    "In ParaView choose Catalyst > Connect on port %s.",
                    self.paraview_host,
                    self.paraview_port,
                    self.paraview_port,
                )
            else:
                LOG.info(
                    "Waiting for ParaView Catalyst Live at %s:%s. "
                    "In ParaView choose Catalyst > Connect on port %s (not Connect to Server). "
                    "Retrying automatically; workflow uploads can arrive before ParaView connects.",
                    self.paraview_host,
                    self.paraview_port,
                    self.paraview_port,
                )
            self.connected = connected
        if connected:
            # The Python link has no extracts-changed getter. InsituUpdate calls
            # ClearAllExtracts (Modified) when the extract list changes, and loads
            # VTK state when the live pipeline changes. Bracket ONLY this call
            # with VTK's global modification clock to conservatively detect both.
            # No VTK work occurs in the upload thread. Idle control exchanges do
            # not modify VTK objects. Do not use wall time or link.GetMTime here:
            # the link itself is not Modified when a new extract is registered.
            stamp = vtkTimeStamp()
            stamp.Modified()
            before = stamp.GetMTime()
            self.link.InsituUpdate(float(self.step), self.step)
            stamp.Modified()
            if stamp.GetMTime() != before + 1:
                self.delivery_pending = True
            if not self.delivery_pending or time.monotonic() < self.next_delivery:
                return
            started = time.monotonic()
            for producer in self.simple.GetSources().values():
                producer.UpdatePipeline()
            self.link.InsituPostProcess(float(self.step), self.step)
            LOG.debug("Delivered Catalyst revision %s", self.step)
            self.delivery_pending = False
            self.step += 1
            finished = time.monotonic()
            self.next_delivery = finished + max(self.live_interval, 2 * (finished - started))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="FlowGraph listening interface")
    parser.add_argument("--port", type=int, default=33333, help="FlowGraph listening port")
    parser.add_argument("--paraview-host", default="127.0.0.1")
    parser.add_argument("--paraview-port", type=int, default=22222)
    parser.add_argument(
        "--interval", type=float, default=0.2, help="Upload and live control polling interval"
    )
    parser.add_argument("--max-sources", type=int, default=128)
    parser.add_argument(
        "--live-interval",
        type=float,
        default=1.0,
        help="Minimum gap between event-driven deliveries (adaptive for slow transfers)",
    )
    parser.add_argument(
        "--allow-origin",
        action="append",
        default=[],
        help="Exact trusted web editor origin, e.g. http://localhost:8082 (repeatable)",
    )
    args = parser.parse_args(argv)
    if not (1 <= args.port <= 65535 and 1 <= args.paraview_port <= 65535):
        parser.error("ports must be between 1 and 65535")
    if (
        not math.isfinite(args.interval)
        or args.interval <= 0
        or args.max_sources < 1
        or not math.isfinite(args.live_interval)
        or args.live_interval <= 0
    ):
        parser.error("interval must be finite and positive; max-sources must be positive")
    for origin in args.allow_origin:
        if "\r" in origin or "\n" in origin:
            parser.error("--allow-origin must not contain CR or LF")
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            parser.error(
                "--allow-origin must be an exact http(s) origin without a path or credentials"
            )
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        gateway = LiveGateway(
            args.paraview_host, args.paraview_port, args.max_sources, args.live_interval
        )
    except ImportError:
        parser.error(f"Run with ParaView's pvpython: pvpython {Path(__file__).resolve()}")
    # Install after ParaView initialization, which may install its own handlers.
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_args: stop.set())
    signal.signal(signal.SIGINT, lambda *_args: stop.set())
    updates = queue.Queue(maxsize=1)
    with GatewayServer((args.host, args.port), updates, tuple(args.allow_origin)) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        LOG.info(
            "Listening for FlowGraph uploads on %s:%s; ParaView Live target %s:%s "
            "(connection not yet confirmed)",
            args.host,
            args.port,
            args.paraview_host,
            args.paraview_port,
        )
        try:
            while not stop.is_set():
                try:
                    gateway.accept(updates.get(timeout=args.interval))
                except queue.Empty:
                    pass
                gateway.tick()
        except KeyboardInterrupt:
            LOG.info("Stopping gateway")
        finally:
            server.shutdown()
            thread.join()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
