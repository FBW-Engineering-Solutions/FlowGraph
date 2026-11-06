"""Bridge conversion, bounded transport and workflow-instance identity."""

import http.client
import json
import logging
import queue
import socket
import threading
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace

import numpy as np
import pytest
from Muscat.MeshTools.MeshCreationTools import CreateMeshOfTriangles
from PIL import Image
from vtkmodules.util.numpy_support import vtk_to_numpy

from flowgraph.adapters.paraview import PARAIEW_BRIDGE, PARAVIEW_BRIDGE
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_web_catalog import workflow_web_catalog
from flowgraph.domain.mesh_document import MeshDocument
from flowgraph.paraview_gateway import (
    HEADER,
    MAX_PAYLOAD,
    GatewayServer,
    LiveGateway,
    Update,
    _HTTPHandler,
    _read_frame,
    _write_frame,
    data_transaction,
    deserialize_dataset,
    main,
    send_dataset,
    serialize_dataset,
    to_vtk,
)


@contextmanager
def receiver(error=None, allowed_origins=(), controls=None, gateway=None):
    updates = queue.Queue(maxsize=1)
    accepted = []
    with GatewayServer(("127.0.0.1", 0), updates, allowed_origins) as server:
        listener = threading.Thread(target=server.serve_forever, daemon=True)
        listener.start()
        stop = threading.Event()

        def consume():
            while not stop.is_set():
                try:
                    update = updates.get(timeout=0.05)
                except queue.Empty:
                    continue
                if update.metadata.get("operation", "dataset") == "dataset":
                    accepted.append(
                        (
                            update.metadata,
                            deserialize_dataset(update.metadata["kind"], update.payload),
                        )
                    )
                elif controls is not None:
                    controls.append(update.metadata)
                if gateway is not None:
                    gateway.accept(update)
                else:
                    update.error = error
                    update.done.set()

        consumer = threading.Thread(target=consume, daemon=True)
        consumer.start()
        try:
            yield server.server_address[1], accepted
        finally:
            server.shutdown()
            stop.set()
            listener.join()
            consumer.join()


def test_mesh_roundtrip_preserves_fields_and_does_not_mutate():
    mesh = CreateMeshOfTriangles(
        np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]), np.array([[0, 1, 2]])
    )
    document = MeshDocument(mesh)
    mesh.nodeFields["temperature"] = np.array([1.0, 2.0, 3.0])
    mesh.elemFields["pressure"] = np.array([4.0])
    original = mesh.nodes.copy()
    result = deserialize_dataset("mesh", serialize_dataset("mesh", to_vtk("mesh", document)))
    assert result.GetNumberOfCells() == 1
    np.testing.assert_array_equal(
        vtk_to_numpy(result.GetPointData().GetArray("temperature")), [1, 2, 3]
    )
    np.testing.assert_array_equal(vtk_to_numpy(result.GetCellData().GetArray("pressure")), [4])
    np.testing.assert_array_equal(mesh.nodes, original)


def test_table_roundtrip_preserves_vectors_strings_and_booleans():
    data = {
        "x": [1, 2],
        "name": ["α", "b"],
        "vector": [[1.0, 2.0], [3.0, 4.0]],
        "flag": [True, False],
    }
    result = deserialize_dataset("table", serialize_dataset("table", to_vtk("table", data)))
    assert result.GetNumberOfRows() == 2
    assert result.GetColumnByName("name").GetValue(0) == "α"
    np.testing.assert_array_equal(vtk_to_numpy(result.GetColumnByName("vector")), data["vector"])
    np.testing.assert_array_equal(vtk_to_numpy(result.GetColumnByName("flag")), [1, 0])


@pytest.mark.parametrize("mode", ["L", "RGB", "RGBA", "I;16", "F", "P", "1"])
def test_image_roundtrip(mode):
    image = Image.new(mode, (3, 2))
    data = to_vtk("image", image)
    result = deserialize_dataset("image", serialize_dataset("image", data))
    assert result.GetDimensions() == (3, 2, 1)
    assert result.GetNumberOfPoints() == 6
    assert image.mode == mode


def test_image_orientation_and_pixels():
    pixels = np.array([[[255, 0, 0], [0, 255, 0]], [[0, 0, 255], [255, 255, 255]]], dtype=np.uint8)
    image = Image.fromarray(pixels)
    data = to_vtk("image", image)
    np.testing.assert_array_equal(
        vtk_to_numpy(data.GetPointData().GetScalars()), pixels[::-1].reshape(-1, 3)
    )
    np.testing.assert_array_equal(np.asarray(image), pixels)


@pytest.mark.parametrize("mode", ["L", "LA", "RGB", "RGBA", "I", "I;16", "F", "P", "1"])
def test_browser_image_xml_preserves_extent_and_pixels(monkeypatch, mode):
    import xml.etree.ElementTree as ET

    import flowgraph.paraview_gateway as gateway

    source = to_vtk("image", Image.new(mode, (7, 5)))
    source.SetOrigin(2, 3, 4)
    source.SetSpacing(0.5, 2, 1)
    with monkeypatch.context() as patch:
        patch.setattr(gateway.sys, "platform", "emscripten")
        payload = serialize_dataset("image", source)
    xml = ET.fromstring(payload)
    assert xml.find("ImageData").get("WholeExtent") == "0 6 0 4 0 0"
    assert xml.find("ImageData/Piece").get("Extent") == "0 6 0 4 0 0"
    result = deserialize_dataset("image", payload)
    assert result.GetDimensions() == (7, 5, 1)
    assert result.GetOrigin() == (2, 3, 4)
    assert result.GetSpacing() == (0.5, 2, 1)
    np.testing.assert_array_equal(
        vtk_to_numpy(result.GetPointData().GetScalars()),
        vtk_to_numpy(source.GetPointData().GetScalars()),
    )


def test_browser_image_xml_preserves_rgb_orientation(monkeypatch):
    import flowgraph.paraview_gateway as gateway

    pixels = np.arange(36, dtype=np.uint8).reshape(3, 4, 3)
    source = to_vtk("image", Image.fromarray(pixels))
    with monkeypatch.context() as patch:
        patch.setattr(gateway.sys, "platform", "emscripten")
        payload = serialize_dataset("image", source)
    result = deserialize_dataset("image", payload)
    np.testing.assert_array_equal(
        vtk_to_numpy(result.GetPointData().GetScalars()), pixels[::-1].reshape(-1, 3)
    )


def test_browser_image_xml_checks_size_before_encoding(monkeypatch):
    import flowgraph.paraview_gateway as gateway

    source = to_vtk("image", Image.new("RGB", (3, 2)))
    monkeypatch.setattr(gateway, "MAX_PAYLOAD", 10)
    with pytest.raises(ValueError, match="size limit"):
        gateway._serialize_browser_image(source)


@pytest.mark.parametrize("size", [(0, 0), (0, 3), (3, 0)])
def test_empty_images_are_rejected_before_upload(size):
    with pytest.raises(ValueError, match="empty image"):
        to_vtk("image", Image.new("RGB", size))


@pytest.mark.parametrize("table", [{"a": [1], "b": [1, 2]}, {"a": [object()]}, {"a": 3}, {"": [1]}])
def test_invalid_tables(table):
    with pytest.raises(ValueError):
        to_vtk("table", table)


def test_instance_sends_id_and_repeated_updates_over_real_sockets():
    registry = create_node_registry()
    assert registry.require("paraview-bridge") is PARAVIEW_BRIDGE is PARAIEW_BRIDGE
    assert PARAVIEW_BRIDGE.cache_policy == "always"
    with receiver() as (port, accepted):
        instance = PARAVIEW_BRIDGE.create_instance("node-α", parameters={"port": port})
        for value in (1, 2):
            assert (
                PARAVIEW_BRIDGE.execute_instance(instance, {"table_1": {"x": [value]}}, registry)
                == {}
            )
    assert [item[0]["node_id"] for item in accepted] == ["node-α", "node-α"]
    assert [vtk_to_numpy(item[1].GetColumnByName("x"))[0] for item in accepted] == [1, 2]


def test_gateway_rejection_and_empty_transaction():
    with (
        receiver(error="source limit") as (port, _accepted),
        pytest.raises(RuntimeError, match="source limit"),
    ):
        send_dataset("node", "table", to_vtk("table", {"x": [1]}), port=port)
    controls = []
    with receiver(controls=controls) as (port, accepted):
        PARAVIEW_BRIDGE.execute_instance(
            PARAVIEW_BRIDGE.create_instance("node", parameters={"port": port}),
            {},
            create_node_registry(),
        )
    assert accepted == []
    assert [item["operation"] for item in controls] == ["begin", "commit"]


def transaction_update(gateway, operation, node="bridge", transaction="tx"):
    update = Update(
        {"version": 1, "node_id": node, "operation": operation, "transaction_id": transaction},
        b"",
    )
    gateway.accept(update)
    return update


def stage_table(gateway, name, value, node="bridge", transaction="tx"):
    metadata = {"node_id": node, "kind": "table", "input_name": name}
    if transaction is not None:
        metadata["transaction_id"] = transaction
    update = Update(metadata, serialize_dataset("table", to_vtk("table", {"x": [value]})))
    gateway.accept(update)
    return update


def test_transaction_commit_prunes_missing_inputs_and_preserves_other_nodes(live_gateway):
    g = live_gateway
    stage_table(g, "table_1", 1, transaction=None)
    stage_table(g, "table_2", 2, transaction=None)
    stage_table(g, "table_1", 9, node="other", transaction=None)
    other_index = g.block_indices[("other", "table_1")]
    removed_index = g.block_indices[("bridge", "table_2")]
    g.delivery_pending = False
    assert transaction_update(g, "begin").error is None
    assert stage_table(g, "table_1", 3).error is None
    assert not g.delivery_pending
    assert g.producers[("bridge", "table_1")].GetColumnByName("x").GetValue(0) == 1
    assert transaction_update(g, "commit").error is None
    assert g.delivery_pending
    assert set(g.producers) == {("bridge", "table_1"), ("other", "table_1")}
    assert g.blocks.GetBlock(removed_index) is None
    assert g.block_indices[("other", "table_1")] == other_index
    assert g.producers[("bridge", "table_1")].GetColumnByName("x").GetValue(0) == 3
    transaction_update(g, "begin")
    transaction_update(g, "commit")
    assert set(g.producers) == {("other", "table_1")}
    assert g.blocks.GetBlock(other_index).GetColumnByName("x").GetValue(0) == 9


def test_transaction_failure_abort_timeout_and_concurrent_begin(live_gateway, monkeypatch):
    g = live_gateway
    stage_table(g, "table_1", 1, transaction=None)
    transaction_update(g, "begin")
    assert "already active" in transaction_update(g, "begin", transaction="second").error
    assert stage_table(g, "table_1", 2).error is None
    bad = Update({"node_id": "bridge", "kind": "table", "transaction_id": "tx"}, b"bad")
    g.accept(bad)
    assert bad.error
    assert "Unknown or expired" in transaction_update(g, "commit").error
    assert g.producers[("bridge", "table_1")].GetColumnByName("x").GetValue(0) == 1
    transaction_update(g, "begin")
    stage_table(g, "table_1", 2)
    assert transaction_update(g, "abort").error is None
    assert not g.transactions
    monkeypatch.setattr("flowgraph.paraview_gateway.time.monotonic", lambda: 0.0)
    transaction_update(g, "begin")
    monkeypatch.setattr("flowgraph.paraview_gateway.time.monotonic", lambda: 61.0)
    assert "Unknown or expired" in transaction_update(g, "commit").error
    assert not g.transactions
    assert g.producers[("bridge", "table_1")].GetColumnByName("x").GetValue(0) == 1


def test_transaction_bounds_and_reuses_removed_block_slots(live_gateway, monkeypatch):
    g = live_gateway
    g.max_sources = 1
    stage_table(g, "old", 1, transaction=None)
    transaction_update(g, "begin")
    stage_table(g, "new", 2)
    assert transaction_update(g, "commit").error is None
    assert g.blocks.GetNumberOfBlocks() == 1
    assert g.block_indices == {("bridge", "new"): 0}
    transaction_update(g, "begin")
    monkeypatch.setattr("flowgraph.paraview_gateway.MAX_PAYLOAD", 1)
    assert "limit" in stage_table(g, "new", 3).error
    assert not g.transactions
    assert g.producers[("bridge", "new")].GetColumnByName("x").GetValue(0) == 2


def test_real_tcp_transaction_replaces_and_clears_node(live_gateway):
    with receiver(gateway=live_gateway) as (port, _):
        with data_transaction("bridge", port=port) as transaction:
            send_dataset(
                "bridge",
                "table",
                to_vtk("table", {"x": [1]}),
                port=port,
                input_name="table_1",
                transaction_id=transaction,
            )
        assert ("bridge", "table_1") in live_gateway.producers
        with (
            pytest.raises(RuntimeError, match="conversion failed"),
            data_transaction("bridge", port=port),
        ):
            raise RuntimeError("conversion failed")
        assert ("bridge", "table_1") in live_gateway.producers
        assert not live_gateway.transactions
        with data_transaction("bridge", port=port):
            pass
        assert not live_gateway.producers


def test_http_transaction_controls_and_staged_dataset(live_gateway):
    origin = "http://localhost:8082"
    with receiver(allowed_origins=(origin,), gateway=live_gateway) as (port, _):
        client = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        base = {"version": 1, "node_id": "browser", "transaction_id": "http-tx"}

        def post(metadata, payload):
            client.request(
                "POST",
                "/api/v1/dataset",
                body=http_frame(metadata, payload),
                headers={"Origin": origin, "Content-Type": "application/octet-stream"},
            )
            response = client.getresponse()
            body = response.read()
            assert response.status == 200, body

        post({**base, "operation": "begin"}, b"")
        post(
            {**base, "kind": "table", "input_name": "table_1"},
            serialize_dataset("table", to_vtk("table", {"x": [42]})),
        )
        assert not live_gateway.producers
        post({**base, "operation": "commit"}, b"")
        assert ("browser", "table_1") in live_gateway.producers
        client.close()


def test_disconnect_edges_then_rerun_replaces_node_snapshot(live_gateway):
    from flowgraph.adapters.data_types import TABLE_DOCUMENT
    from flowgraph.application.workflow_core import (
        NodeDefinition,
        PortDefinition,
        PortDirection,
        WorkflowEdge,
        WorkflowExecutor,
        WorkflowGraph,
    )

    source = NodeDefinition(
        id="transaction-source",
        label="Table",
        icon="",
        ports=(PortDefinition("table", PortDirection.OUTPUT, TABLE_DOCUMENT),),
        executor=lambda _i, _p: {"table": {"x": [1]}},
    )
    registry = create_node_registry()
    registry.register(source)
    with receiver(gateway=live_gateway) as (port, _):
        graph = WorkflowGraph(
            [
                source.create_instance("source"),
                PARAVIEW_BRIDGE.create_instance("bridge", parameters={"port": port}),
            ]
        )
        edges = [WorkflowEdge("source", "table", "bridge", f"table_{i}") for i in (1, 2)]
        for edge in edges:
            graph.add_edge(edge, registry)
        WorkflowExecutor(registry).run(graph)
        assert len(live_gateway.producers) == 2
        graph.remove_edge(edges[1], registry)
        WorkflowExecutor(registry).run(graph)
        assert set(live_gateway.producers) == {("bridge", "table_1")}
        graph.remove_edge(edges[0], registry)
        WorkflowExecutor(registry).run(graph)
        assert not live_gateway.producers


def test_browser_transaction_uses_http_for_begin_data_and_commit(monkeypatch):
    sent = []
    monkeypatch.setattr("flowgraph.paraview_gateway.sys.platform", "emscripten")
    monkeypatch.setattr(
        "flowgraph.paraview_gateway._send_browser_dataset",
        lambda _h, _p, _t, m, b: sent.append((m, b)),
    )
    with data_transaction("browser") as transaction:
        send_dataset(
            "browser",
            "table",
            to_vtk("table", {"x": [1]}),
            transaction_id=transaction,
            input_name="table_1",
        )
    assert [m.get("operation", "dataset") for m, _ in sent] == ["begin", "dataset", "commit"]
    assert {m["transaction_id"] for m, _ in sent} == {transaction}
    assert sent[0][1] == sent[2][1] == b""


def test_two_bridge_instances_send_distinct_node_ids_over_real_sockets():
    registry = create_node_registry()
    with receiver() as (port, accepted):
        for node_id, value in (("bridge-first", 1), ("bridge-second", 2), ("bridge-first", 3)):
            instance = PARAVIEW_BRIDGE.create_instance(node_id, parameters={"port": port})
            PARAVIEW_BRIDGE.execute_instance(instance, {"table_1": {"x": [value]}}, registry)
    assert [metadata["node_id"] for metadata, _dataset in accepted] == [
        "bridge-first",
        "bridge-second",
        "bridge-first",
    ]
    assert [dataset.GetColumnByName("x").GetValue(0) for _metadata, dataset in accepted] == [
        1,
        2,
        3,
    ]


def test_malformed_frames_are_bounded():
    left, right = socket.socketpair()
    try:
        left.sendall(HEADER.pack(1, MAX_PAYLOAD + 1))
        with pytest.raises(ValueError, match="size limit"):
            _read_frame(right)
    finally:
        left.close()
        right.close()


def test_truncated_frames():
    left, right = socket.socketpair()
    left.close()
    try:
        with pytest.raises(ValueError, match="Truncated"):
            _read_frame(right)
    finally:
        right.close()


@pytest.mark.parametrize(
    ("header", "message"),
    [
        (b"GET / HTTP/1", "HTTP/WebSocket"),
        (b"POST / HTTP/", "HTTP/WebSocket"),
        (b"OPTIONS / HT", "HTTP/WebSocket"),
        (b'{"command": ', "Unframed JSON"),
        (b"\x16\x03" + b"\x00" * 10, "TLS received"),
    ],
)
def test_wrong_protocol_is_not_reported_as_large_dataset(header, message):
    left, right = socket.socketpair()
    try:
        assert len(header) == HEADER.size
        left.sendall(header)
        with pytest.raises(ValueError, match=message):
            _read_frame(right)
    finally:
        left.close()
        right.close()


def test_invalid_header_reports_lengths_and_hex():
    left, right = socket.socketpair()
    try:
        header = HEADER.pack(25, MAX_PAYLOAD + 1)
        left.sendall(header)
        with pytest.raises(
            ValueError, match=f"metadata=25.*payload={MAX_PAYLOAD + 1}.*{header.hex()}"
        ):
            _read_frame(right)
    finally:
        left.close()
        right.close()


def test_server_handles_http_without_parsing_as_tcp_lengths(caplog):
    with (
        receiver() as (port, _accepted),
        socket.create_connection(("127.0.0.1", port), timeout=2) as sock,
    ):
        sock.sendall(b"GET / HTTP/1.1\r\n\r\n")
        response = http.client.HTTPResponse(sock)
        response.begin()
        assert response.status == 200
        assert json.loads(response.read())["status"] == "listening"


def test_websocket_get_explains_stale_worker(caplog):
    with receiver() as (port, accepted):
        client = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        client.request("GET", "/", headers={"Upgrade": "websocket", "Connection": "Upgrade"})
        reply = client.getresponse()
        assert reply.status == 426
        assert "old WASM worker" in json.loads(reply.read())["error"]
        client.close()
        assert accepted == []
    assert "WebSocket client detected" in caplog.text


@pytest.mark.parametrize("path", ["/", "/health", "/missing"])
def test_health_is_reachability_only(path):
    with receiver() as (port, accepted):
        client = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        client.request("GET", path)
        reply = client.getresponse()
        assert reply.status == (404 if path == "/missing" else 200)
        data = json.loads(reply.read())
        if path != "/missing":
            assert data["service"] == "flowgraph-paraview-gateway"
            assert "Catalyst connection" in data["note"]
            assert "datasets" not in data
        client.close()
        assert accepted == []


def http_frame(metadata=None, payload=None):
    metadata = (
        {"version": 1, "node_id": "wasm-node", "kind": "table"} if metadata is None else metadata
    )
    payload = (
        serialize_dataset("table", to_vtk("table", {"x": [42]})) if payload is None else payload
    )
    encoded = json.dumps(metadata).encode()
    return HEADER.pack(len(encoded), len(payload)) + encoded + payload


@pytest.mark.parametrize("origin", ["http://localhost:8082", "https://editor.example"])
def test_http_upload_preflight_and_native_on_same_port(origin):
    with receiver(allowed_origins=("http://localhost:8082", "https://editor.example")) as (
        port,
        accepted,
    ):
        client = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        client.request(
            "OPTIONS",
            "/api/v1/dataset",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
                "Access-Control-Request-Private-Network": "true",
            },
        )
        reply = client.getresponse()
        assert reply.status == 200
        assert reply.getheader("Access-Control-Allow-Origin") == origin
        assert reply.getheader("Access-Control-Allow-Private-Network") == "true"
        reply.read()
        client.request(
            "POST",
            "/api/v1/dataset",
            body=http_frame(),
            headers={
                "Origin": origin,
                "Content-Type": "application/octet-stream",
            },
        )
        reply = client.getresponse()
        assert reply.status == 200
        assert reply.getheader("Access-Control-Allow-Origin") == origin
        assert json.loads(reply.read())["ok"]
        client.close()
        send_dataset("native-node", "table", to_vtk("table", {"x": [7]}), port=port)
    assert [metadata["node_id"] for metadata, _data in accepted] == ["wasm-node", "native-node"]


@pytest.mark.parametrize(
    "origin", [None, "null", "https://untrusted.example", "http://localhost:8082.evil"]
)
def test_http_denies_untrusted_origin(origin):
    with receiver(allowed_origins=("http://localhost:8082",)) as (port, accepted):
        client = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        headers = {"Content-Type": "application/octet-stream"}
        if origin is not None:
            headers["Origin"] = origin
        client.request("POST", "/api/v1/dataset", http_frame(), headers)
        reply = client.getresponse()
        assert reply.status == 403
        assert reply.getheader("Access-Control-Allow-Origin") is None
        assert "--allow-origin" in reply.read().decode()
        client.close()
        assert accepted == []


def test_http_reply_uses_configured_origin_value():
    configured_origin = "http://localhost:8082"
    request_origin = configured_origin.encode().decode()
    assert request_origin == configured_origin
    assert request_origin is not configured_origin
    headers = []
    handler = SimpleNamespace(
        headers={"Origin": request_origin},
        server=SimpleNamespace(allowed_origins=(configured_origin,)),
        send_response=lambda status: None,
        send_header=lambda name, value: headers.append((name, value)),
        end_headers=lambda: None,
        wfile=SimpleNamespace(write=lambda body: None),
    )

    _HTTPHandler._reply(handler, 200)

    origins = [value for name, value in headers if name == "Access-Control-Allow-Origin"]
    assert len(origins) == 1
    assert origins[0] is configured_origin


@pytest.mark.parametrize("newline", ["\r", "\n", "\r\n"])
@pytest.mark.parametrize("position", ["leading", "embedded", "trailing"])
def test_allow_origin_rejects_newlines(newline, position, capsys):
    origin = {
        "leading": f"{newline}http://localhost:8082",
        "embedded": f"http://local{newline}host:8082",
        "trailing": f"http://localhost:8082{newline}",
    }[position]
    with pytest.raises(ValueError, match="must not contain CR or LF"):
        GatewayServer(("127.0.0.1", 0), queue.Queue(), (origin,))
    with pytest.raises(SystemExit) as caught:
        main(["--allow-origin", origin])
    assert caught.value.code == 2
    assert "--allow-origin must not contain CR or LF" in capsys.readouterr().err


@pytest.mark.parametrize("body", [b"bad", HEADER.pack(100, 100) + b"x", http_frame([], b"xml")])
def test_http_rejects_malformed_body(body):
    origin = "http://localhost:8082"
    with receiver(allowed_origins=(origin,)) as (port, accepted):
        client = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        client.request(
            "POST",
            "/api/v1/dataset",
            body,
            {
                "Origin": origin,
                "Content-Type": "application/octet-stream",
            },
        )
        reply = client.getresponse()
        assert reply.status == 400
        assert not json.loads(reply.read())["ok"]
        client.close()
        assert accepted == []


def test_emscripten_selects_http(monkeypatch):
    calls = []
    monkeypatch.setattr("flowgraph.paraview_gateway.sys.platform", "emscripten")
    monkeypatch.setattr(
        "flowgraph.paraview_gateway._send_browser_dataset", lambda *args: calls.append(args)
    )
    send_dataset("wasm", "table", to_vtk("table", {"x": [1]}))
    host, port, timeout, metadata, payload = calls[0]
    assert (host, port, timeout) == ("127.0.0.1", 33333, 10.0)
    assert metadata == {"version": 1, "node_id": "wasm", "kind": "table"}
    assert deserialize_dataset("table", payload).GetNumberOfRows() == 1


@pytest.mark.parametrize(
    "origin",
    ["*", "null", "http://localhost:8082/", "https://user:password@host", "http://localhost/path"],
)
def test_allow_origin_rejects_non_origins(origin):
    with pytest.raises(SystemExit) as caught:
        main(["--allow-origin", origin])
    assert caught.value.code == 2


def test_server_rejects_invalid_metadata():
    with (
        receiver() as (port, _accepted),
        socket.create_connection(("127.0.0.1", port), timeout=2) as sock,
    ):
        _write_frame(sock, {"version": 5}, b"invalid")
        reply, _ = _read_frame(sock)
        assert reply["ok"] is False


def test_malformed_xml():
    with pytest.raises(ValueError, match="Invalid VTK"):
        deserialize_dataset("table", b"not xml")


@pytest.mark.parametrize("parameters", [{"timeout": 0}, {"timeout": float("nan")}, {"port": 0}])
def test_invalid_connection_parameters(parameters):
    with pytest.raises(ValueError):
        send_dataset("node", "table", to_vtk("table", {}), **parameters)


def test_help_does_not_require_paraview(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["--help"])
    assert caught.value.code == 0
    assert "--paraview-port" in capsys.readouterr().out


def test_catalog_contains_bridge():
    assert "paraview-bridge" in str(workflow_web_catalog())


@pytest.fixture
def live_gateway():
    """Exercise real VTK blocks without requiring ParaView's Python runtime."""
    from vtkmodules.vtkCommonDataModel import vtkMultiBlockDataSet

    class Producer:
        def GetClientSideObject(self):
            return self

        def SetOutput(self, dataset):
            self.dataset = dataset

        def UpdatePipeline(self):
            pass

        def Modified(self):
            pass

    gateway = LiveGateway.__new__(LiveGateway)
    gateway.producers = {}
    gateway.blocks = vtkMultiBlockDataSet()
    gateway.block_indices = {}
    gateway.output = Producer()
    gateway.max_sources = 128
    return gateway


def test_live_gateway_keeps_two_node_meshes_and_replaces_only_matching_block(live_gateway):
    from vtkmodules.vtkCommonDataModel import vtkCompositeDataSet

    gateway = live_gateway
    for node_id, offset in (("bridge-first", 0), ("bridge-second", 10), ("bridge-first", 20)):
        mesh = CreateMeshOfTriangles(
            np.array([[offset, 0.0, 0.0], [offset + 1, 0.0, 0.0], [offset, 1.0, 0.0]]),
            np.array([[0, 1, 2]]),
        )
        update = Update(
            {"node_id": node_id, "kind": "mesh"},
            serialize_dataset("mesh", to_vtk("mesh", MeshDocument(mesh))),
        )
        gateway.accept(update)
        assert update.done.is_set() and update.error is None
        if node_id == "bridge-second":
            second = gateway.blocks.GetBlock(1)
    assert gateway.blocks.GetNumberOfBlocks() == 2
    assert len(gateway.producers) == 2
    assert gateway.output.dataset is gateway.blocks
    assert gateway.blocks.GetBlock(1) is second
    for index, (node_id, offset) in enumerate((("bridge-first", 20), ("bridge-second", 10))):
        block = gateway.blocks.GetBlock(index)
        assert block.GetNumberOfCells() == 1
        assert block.GetBounds() == (offset, offset + 1, 0, 1, 0, 0)
        assert (
            gateway.blocks.GetMetaData(index).Get(vtkCompositeDataSet.NAME()) == f"{node_id}/mesh"
        )
        assert (
            block.GetFieldData().GetAbstractArray("flowgraph_workflow_node_id").GetValue(0)
            == node_id
        )


def test_live_gateway_keeps_multiple_input_kinds_on_one_node(live_gateway):
    gateway = live_gateway
    for kind, value in (("table", {"x": [1, 2]}), ("image", Image.new("RGB", (3, 2)))):
        update = Update(
            {"node_id": "bridge", "kind": kind}, serialize_dataset(kind, to_vtk(kind, value))
        )
        gateway.accept(update)
        assert update.done.is_set() and update.error is None
    assert gateway.blocks.GetNumberOfBlocks() == 2
    assert gateway.blocks.GetBlock(0).GetNumberOfRows() == 2
    assert gateway.blocks.GetBlock(1).GetDimensions() == (3, 2, 1)


@pytest.mark.parametrize("mode", ["L", "LA", "RGB", "RGBA", "I", "I;16", "F", "P", "1"])
def test_gateway_image_blocks_keep_pixels_on_resize_and_second_input(live_gateway, mode, caplog):
    gateway = live_gateway
    with caplog.at_level(logging.INFO, logger="flowgraph.paraview_gateway"):
        for input_name, size in (("image_1", (3, 2)), ("image_2", (2, 4)), ("image_1", (5, 3))):
            source = to_vtk("image", Image.new(mode, size))
            update = Update(
                {"node_id": "bridge", "kind": "image", "input_name": input_name},
                serialize_dataset("image", source),
            )
            gateway.accept(update)
            assert update.error is None
            block = gateway.blocks.GetBlock(gateway.block_indices[("bridge", input_name)])
            assert block.GetDimensions() == (*size, 1)
            assert block.GetNumberOfPoints() == size[0] * size[1]
            assert block.GetNumberOfCells() == (size[0] - 1) * (size[1] - 1)
            np.testing.assert_array_equal(
                vtk_to_numpy(block.GetPointData().GetScalars()),
                vtk_to_numpy(source.GetPointData().GetScalars()),
            )
    assert gateway.blocks.GetNumberOfBlocks() == 2
    assert gateway.blocks.GetBlock(1).GetNumberOfPoints() == 8
    assert "dimensions=(5, 3, 1)" in caplog.text
    assert "points=15, cells=8" in caplog.text


def test_gateway_rejects_image_without_pixels_and_keeps_previous_block(live_gateway):
    from vtkmodules.vtkCommonDataModel import vtkImageData

    valid = Update(
        {"node_id": "bridge", "kind": "image"},
        serialize_dataset("image", to_vtk("image", Image.new("RGB", (3, 2)))),
    )
    live_gateway.accept(valid)
    assert valid.error is None
    invalid_image = vtkImageData()
    invalid_image.SetDimensions(3, 2, 1)
    invalid = Update(valid.metadata, serialize_dataset("image", invalid_image))
    live_gateway.accept(invalid)
    assert invalid.done.is_set()
    assert "no pixels" in invalid.error
    assert live_gateway.blocks.GetBlock(0).GetNumberOfPoints() == 6


def test_expandable_inputs_keep_identity_through_transport_and_gateway(live_gateway):
    from vtkmodules.vtkCommonDataModel import vtkCompositeDataSet

    registry = create_node_registry()
    with receiver() as (port, accepted):
        instance = PARAVIEW_BRIDGE.create_instance("bridge", parameters={"port": port})
        for value in (1, 3):
            PARAVIEW_BRIDGE.execute_instance(
                instance,
                {"table_1": {"x": [value]}, "table_2": {"x": [2]}, "table_3": {"x": [4]}},
                registry,
            )
    assert [metadata.get("input_name", metadata["kind"]) for metadata, _ in accepted] == [
        "table_1",
        "table_2",
        "table_3",
        "table_1",
        "table_2",
        "table_3",
    ]
    for metadata, dataset in accepted:
        metadata = {key: value for key, value in metadata.items() if key != "transaction_id"}
        update = Update(metadata, serialize_dataset(metadata["kind"], dataset))
        live_gateway.accept(update)
        assert update.error is None
    assert live_gateway.blocks.GetNumberOfBlocks() == 3
    assert [live_gateway.blocks.GetBlock(i).GetColumnByName("x").GetValue(0) for i in range(3)] == [
        3,
        2,
        4,
    ]
    assert [
        live_gateway.blocks.GetMetaData(i).Get(vtkCompositeDataSet.NAME()) for i in range(3)
    ] == ["bridge/table_1", "bridge/table_2", "bridge/table_3"]


def test_expandable_bridge_sends_all_families(monkeypatch):
    monkeypatch.setattr(
        "flowgraph.adapters.paraview.data_transaction", lambda *a, **k: nullcontext("test")
    )
    calls = []
    monkeypatch.setattr("flowgraph.adapters.paraview.to_vtk", lambda kind, value: (kind, value))
    monkeypatch.setattr(
        "flowgraph.adapters.paraview.send_dataset",
        lambda *args, **kwargs: calls.append((args, kwargs.get("input_name"))),
    )
    PARAVIEW_BRIDGE.execute_instance(
        PARAVIEW_BRIDGE.create_instance("bridge"),
        {"mesh_1": 1, "mesh_2": 2, "table_1": 3, "image_1": 4},
        create_node_registry(),
    )
    assert calls == [
        (("bridge", "mesh", ("mesh", 1)), "mesh_1"),
        (("bridge", "mesh", ("mesh", 2)), "mesh_2"),
        (("bridge", "table", ("table", 3)), "table_1"),
        (("bridge", "image", ("image", 4)), "image_1"),
    ]


def test_expandable_bridge_graph_grows_and_executes(monkeypatch):
    monkeypatch.setattr(
        "flowgraph.adapters.paraview.data_transaction", lambda *a, **k: nullcontext("test")
    )
    from flowgraph.adapters.data_types import TABLE_DOCUMENT
    from flowgraph.application.workflow_core import (
        NodeDefinition,
        PortDefinition,
        PortDirection,
        WorkflowEdge,
        WorkflowExecutor,
        WorkflowGraph,
    )

    calls = []
    monkeypatch.setattr(
        "flowgraph.adapters.paraview.send_dataset",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    source = NodeDefinition(
        id="bridge-test-source",
        label="Tables",
        icon="",
        ports=(PortDefinition("table", PortDirection.OUTPUT, TABLE_DOCUMENT),),
        executor=lambda _inputs, _parameters: {"table": {"x": [1]}},
    )
    registry = create_node_registry()
    registry.register(source)
    graph = WorkflowGraph(
        [
            source.create_instance("a"),
            source.create_instance("b"),
            PARAVIEW_BRIDGE.create_instance("sink"),
        ]
    )
    for index, node_id in enumerate(("a", "b"), 1):
        graph.add_edge(WorkflowEdge(node_id, "table", "sink", f"table_{index}"), registry)
    names = [port.name for port in PARAVIEW_BRIDGE.ports_for_instance(graph.require_node("sink"))]
    assert "table_3" in names
    WorkflowExecutor(registry).run(graph)
    assert [kwargs["input_name"] for _args, kwargs in calls] == ["table_1", "table_2"]


@pytest.mark.parametrize("kind", ["mesh", "table", "image"])
def test_expandable_bridge_caps_each_family_at_ten(kind):
    from flowgraph.application.workflow_core import (
        NodeDefinition,
        PortDefinition,
        PortDirection,
        WorkflowEdge,
        WorkflowGraph,
        WorkflowValidationError,
    )

    template = next(port for port in PARAVIEW_BRIDGE.ports if port.name == kind)
    source = NodeDefinition(
        id="bridge-limit-source",
        label="Source",
        icon="",
        ports=(PortDefinition("data", PortDirection.OUTPUT, template.data_type),),
        executor=lambda _inputs, _parameters: {},
    )
    registry = create_node_registry()
    registry.register(source)
    sink = PARAVIEW_BRIDGE.create_instance("sink")
    graph = WorkflowGraph([source.create_instance("source"), sink])
    for index in range(1, 11):
        graph.add_edge(WorkflowEdge("source", "data", "sink", f"{kind}_{index}"), registry)
        names = [port.name for port in PARAVIEW_BRIDGE.ports_for_instance(sink)]
        assert f"{kind}_{min(index + 1, 10)}" in names
    assert [name for name in names if name.startswith(f"{kind}_")] == [
        f"{kind}_{index}" for index in range(1, 11)
    ]
    with pytest.raises(WorkflowValidationError):
        graph.add_edge(WorkflowEdge("source", "data", "sink", f"{kind}_11"), registry)


@pytest.mark.parametrize("kind", ["mesh", "table", "image"])
def test_expandable_bridge_sends_ten_slots_in_numeric_order(kind, monkeypatch):
    monkeypatch.setattr(
        "flowgraph.adapters.paraview.data_transaction", lambda *a, **k: nullcontext("test")
    )
    calls = []
    monkeypatch.setattr("flowgraph.adapters.paraview.to_vtk", lambda _kind, value: value)
    monkeypatch.setattr(
        "flowgraph.adapters.paraview.send_dataset",
        lambda *args, **kwargs: calls.append((args, kwargs["input_name"])),
    )
    PARAVIEW_BRIDGE.execute_instance(
        PARAVIEW_BRIDGE.create_instance("bridge"),
        {f"{kind}_{index}": index for index in range(10, 0, -1)},
        create_node_registry(),
    )
    assert calls == [(("bridge", kind, index), f"{kind}_{index}") for index in range(1, 11)]


def test_http_expandable_input_identity():
    origin = "http://localhost:8082"
    with receiver(allowed_origins=(origin,)) as (port, accepted):
        client = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        client.request(
            "POST",
            "/api/v1/dataset",
            body=http_frame(
                metadata={
                    "version": 1,
                    "node_id": "browser",
                    "kind": "table",
                    "input_name": "table_2",
                }
            ),
            headers={"Origin": origin, "Content-Type": "application/octet-stream"},
        )
        response = client.getresponse()
        assert response.status == 200
        response.read()
        client.close()
    assert accepted[0][0]["input_name"] == "table_2"


@pytest.mark.parametrize("input_name", ["", 2, False])
def test_invalid_input_identity(input_name):
    with pytest.raises(ValueError, match="input_name"):
        send_dataset("bridge", "table", to_vtk("table", {}), input_name=input_name)


def test_live_gateway_replaces_sources_adds_identity_and_bounds_retention():
    from vtkmodules.vtkCommonDataModel import vtkCompositeDataSet, vtkMultiBlockDataSet

    created = []

    class Producer:
        def __init__(self, registrationName):
            self.name = registrationName
            created.append(self)

        def GetClientSideObject(self):
            return self

        def SetOutput(self, dataset):
            self.dataset = dataset

        def UpdatePipeline(self):
            pass

        def Modified(self):
            pass

    gateway = LiveGateway.__new__(LiveGateway)
    gateway.simple = SimpleNamespace(PVTrivialProducer=Producer)
    gateway.producers = {}
    gateway.blocks = vtkMultiBlockDataSet()
    gateway.block_indices = {}
    gateway.output = Producer("FlowGraph outputs")
    gateway.max_sources = 1
    for value in (1, 2):
        update = Update(
            {"node_id": "node", "kind": "table"},
            serialize_dataset("table", to_vtk("table", {"x": [value]})),
        )
        gateway.accept(update)
        assert update.done.is_set() and update.error is None
    assert len(created) == 1
    assert created[0].name == "FlowGraph outputs"
    assert created[0].dataset.GetNumberOfBlocks() == 1
    assert gateway.blocks.GetMetaData(0).Get(vtkCompositeDataSet.NAME()) == "node/table"
    assert gateway.blocks.GetBlock(0).GetColumnByName("x").GetValue(0) == 2
    assert (
        gateway.blocks.GetBlock(0)
        .GetFieldData()
        .GetAbstractArray("flowgraph_workflow_node_id")
        .GetValue(0)
        == "node"
    )
    rejected = Update({"node_id": "other", "kind": "table"}, update.payload)
    gateway.accept(rejected)
    assert "source limit" in rejected.error
    invalid = Update({"node_id": "node", "kind": "table"}, b"invalid")
    gateway.accept(invalid)
    assert invalid.error and invalid.done.is_set()
    assert gateway.blocks.GetBlock(0).GetColumnByName("x").GetValue(0) == 2


def test_instance_publishes_all_connected_inputs(monkeypatch):
    monkeypatch.setattr(
        "flowgraph.adapters.paraview.data_transaction", lambda *a, **k: nullcontext("test")
    )
    calls = []
    monkeypatch.setattr(
        "flowgraph.adapters.paraview.send_dataset", lambda *args, **kw: calls.append(args)
    )
    monkeypatch.setattr("flowgraph.adapters.paraview.to_vtk", lambda name, value: value)
    instance = PARAVIEW_BRIDGE.create_instance("bridge")
    PARAVIEW_BRIDGE.execute_instance(
        instance, {"mesh_1": 1, "table_1": 2, "image_1": 3}, create_node_registry()
    )
    assert calls == [("bridge", "mesh", 1), ("bridge", "table", 2), ("bridge", "image", 3)]


def test_socket_timeout_surfaces_actionable_error():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with pytest.raises(RuntimeError, match="ParaView gateway.*timed out"):
            send_dataset(
                "node", "table", to_vtk("table", {}), port=listener.getsockname()[1], timeout=0.05
            )


def test_live_connection_logs_wait_connect_disconnect_and_reconnect(caplog, monkeypatch):
    monkeypatch.setattr("flowgraph.paraview_gateway.time.monotonic", lambda: 0.0)
    states = iter([False, False, True, True, False, False, True])
    updates = []
    gateway = LiveGateway.__new__(LiveGateway)
    gateway.paraview_host = "localhost"
    gateway.paraview_port = 22224
    gateway.connected = None
    gateway.live_interval = 0.0
    gateway.next_delivery = 0.0
    gateway.step = 0
    gateway.manager = object()
    gateway.link = SimpleNamespace(
        Initialize=lambda _manager: next(states),
        InsituUpdate=lambda *args: updates.append(("update", args)),
        InsituPostProcess=lambda *args: updates.append(("post", args)),
    )
    gateway.simple = SimpleNamespace(GetSources=dict)
    with caplog.at_level(logging.INFO, logger="flowgraph.paraview_gateway"):
        for _ in range(7):
            gateway.tick()
    messages = [record.getMessage() for record in caplog.records]
    assert len(messages) == 4
    assert messages[0].startswith("Waiting for ParaView Catalyst Live at localhost:22224")
    assert "Catalyst > Connect" in messages[0]
    assert messages[1].startswith("Connected to ParaView Catalyst Live at localhost:22224")
    assert "Extract 'FlowGraph outputs'" in messages[1]
    assert messages[2].startswith("Disconnected from ParaView Catalyst Live at localhost:22224")
    assert "retrying" in messages[2]
    assert messages[3] == messages[1]
    assert [args[1] for kind, args in updates if kind == "update"] == [0, 1, 1]
    assert [args[1] for kind, args in updates if kind == "post"] == [0, 1]
    assert gateway.step == 2


def test_live_connection_can_succeed_on_first_poll(caplog, monkeypatch):
    monkeypatch.setattr("flowgraph.paraview_gateway.time.monotonic", lambda: 0.0)
    gateway = LiveGateway.__new__(LiveGateway)
    gateway.paraview_host = "127.0.0.1"
    gateway.paraview_port = 22222
    gateway.connected = None
    gateway.live_interval = 0.0
    gateway.next_delivery = 0.0
    gateway.step = 0
    gateway.manager = object()
    gateway.link = SimpleNamespace(
        Initialize=lambda _manager: True,
        InsituUpdate=lambda *_args: None,
        InsituPostProcess=lambda *_args: None,
    )
    gateway.simple = SimpleNamespace(GetSources=dict)
    with caplog.at_level(logging.INFO, logger="flowgraph.paraview_gateway"):
        gateway.tick()
        gateway.tick()
    assert gateway.step == 1  # idle polling does not publish another timestep
    assert len(caplog.records) == 1
    assert caplog.records[0].getMessage().startswith("Connected to ParaView")


def test_live_delivery_leaves_adaptive_idle_gap_after_slow_transfer(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("flowgraph.paraview_gateway.time.monotonic", lambda: clock[0])
    gateway = LiveGateway.__new__(LiveGateway)
    gateway.live_interval = 1.0
    gateway.next_delivery = 0.0
    gateway.paraview_host = "localhost"
    gateway.paraview_port = 22224
    gateway.connected = True
    gateway.delivery_pending = True
    gateway.step = 0
    gateway.manager = object()
    deliveries = []

    def deliver(*_args):
        deliveries.append(clock[0])
        clock[0] += 2.0

    gateway.link = SimpleNamespace(
        Initialize=lambda _manager: True,
        InsituUpdate=lambda *_args: None,
        InsituPostProcess=deliver,
    )
    gateway.simple = SimpleNamespace(GetSources=dict)
    gateway.tick()
    assert deliveries == [0.0]
    assert gateway.next_delivery == 6.0
    clock[0] = 5.9
    gateway.delivery_pending = True
    gateway.tick()
    assert deliveries == [0.0]
    assert gateway.step == 1
    clock[0] = 6.0
    gateway.tick()
    assert deliveries == [0.0, 6.0]
    assert gateway.step == 2


def test_live_delivery_detects_late_extract_without_repeated_idle_transfers(monkeypatch):
    from vtkmodules.vtkCommonCore import vtkTimeStamp

    monkeypatch.setattr("flowgraph.paraview_gateway.time.monotonic", lambda: 100.0)
    gateway = LiveGateway.__new__(LiveGateway)
    gateway.connected = True
    gateway.delivery_pending = False
    gateway.next_delivery = 0.0
    gateway.live_interval = 0.0
    gateway.step = 3
    gateway.manager = object()
    gateway.simple = SimpleNamespace(GetSources=dict)
    changed = vtkTimeStamp()
    controls = []
    deliveries = []

    def control(*args):
        controls.append(args)
        if len(controls) == 2:
            changed.Modified()  # ClearAllExtracts does this for an extract request

    gateway.link = SimpleNamespace(
        Initialize=lambda _: True,
        InsituUpdate=control,
        InsituPostProcess=lambda *args: deliveries.append(args),
    )
    for _ in range(6):
        gateway.tick()
    assert len(controls) == 6
    assert deliveries == [(3.0, 3)]
    assert gateway.step == 4
    assert gateway.delivery_pending is False


def test_live_gateway_marks_only_accepted_uploads_for_delivery(live_gateway):
    gateway = live_gateway
    gateway.delivery_pending = False
    bad = Update({"node_id": "node", "kind": "image"}, b"invalid")
    gateway.accept(bad)
    assert bad.error is not None
    assert gateway.delivery_pending is False
    good = Update(
        {"node_id": "node", "kind": "table"},
        serialize_dataset("table", to_vtk("table", {"x": [1]})),
    )
    gateway.accept(good)
    assert good.error is None
    assert gateway.delivery_pending is True


@pytest.mark.parametrize("interval", ["0", "-1", "nan", "inf"])
def test_gateway_rejects_invalid_live_interval(interval):
    with pytest.raises(SystemExit) as error:
        main(["--live-interval", interval])
    assert error.value.code == 2
