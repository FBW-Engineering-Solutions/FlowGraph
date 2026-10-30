---
id: reference.adapters.sinks
title: Sink Nodes
section: Reference
order: 19
description: Nodes that consume data in application views.
---

# Sink nodes

## To 3D View (`mesh-sink`)

Requires `mesh: Mesh document` and has no outputs. The node displays the
canonical mesh in the 3D view. UI-only parameters are `color_field=""` (solid
color), `show_representation=True`, and `show_axis_grid=False`. The color-field
menu lists finite numeric nodal fields. Multi-component nodal fields are colored
by their vector magnitude. Elemental fields and direct RGB/RGBA colors are not
yet available in the browser's Plotly surface preview. The WASM runtime returns
triangulated surface coordinates and field values only for connected `mesh-sink`
nodes; it does not serialize the full mesh into the browser.

## Show Image (`local-view`)

Requires one `input: Image` input and has no outputs. After execution, the node displays
the Pillow image in its own embedded viewport. The node has no configurable parameters.

The execution response contains a PNG preview limited to 1024 pixels on its longest
side, preserving aspect ratio and transparency. Smaller images are not enlarged.
The original image is never resized or modified: workflow processing and exports
keep full resolution. The displayed dimensions and mouse-coordinate readout refer
to the original image, with zero-based coordinates, even in the expanded viewport.
Preview payloads retain original `width`, `height`, and `mode`; `preview_width` and
`preview_height` describe the encoded PNG. Only Show Image inputs produce image
previews; multiple viewers sharing an image reuse its encoding within a response.

## Show Value (`show-value`)

Accepts `value: Any` and has no outputs. After execution, the node displays the
input's Python `str()` representation on the workflow using the same presentation
style as the Paragraph documentation node. Any value type can be connected to its
input.

## Plot Table (`plot-table`)

Requires `table: Table document` as its only input and has no outputs or
parameters. The workflow view plots numeric list-valued columns in the table;
non-numeric columns are not plotted. Plotting is handled by the presentation,
not by the headless node executor.

## Send to ParaView (`paraview-bridge`)

Sends connected `mesh: Mesh document`, `table: Table`, and/or `image: Image`
inputs to a persistent gateway. At least one must be connected. There are no
outputs. Parameters are `host="127.0.0.1"`, `port=33333`, and `timeout=10.0`
seconds. Every execution sends data, including incremental runs with unchanged
inputs; the node's cache policy is `always`.

### Start the gateway

Use the **pvpython from the same ParaView installation as the GUI**. The script
is standalone and needs no FlowGraph/Muscat/Pillow installation in pvpython.
From this source checkout, for example:

```bash
/home/fbw/Apps/ParaView-6.2.0-MPI-Linux-Python3.12-x86_64/bin/pvpython --no-mpi \
  /home/fbw/repos/FlowGraph/FlowGraph/src/flowgraph/paraview_gateway.py
```

For a wheel installation, locate the script using the FlowGraph environment:

```bash
uv run python -c 'import flowgraph.paraview_gateway as g; print(g.__file__)'
```

Run that absolute filename with pvpython. In ParaView choose **Catalyst →
Connect**, accepting port **22222**. ParaView listens; the gateway connects to
it. Workflow nodes connect to the gateway on **33333**. The gateway retries the
live connection while idle and retains data received before ParaView connects.
No rendering window is created by the gateway.

The startup `Listening for FlowGraph uploads` message confirms only the upload
server, **not** the ParaView connection. The gateway separately logs:

```text
Waiting for ParaView Catalyst Live at 127.0.0.1:22222. ...
Connected to ParaView Catalyst Live at 127.0.0.1:22222. ...
Disconnected from ParaView Catalyst Live at 127.0.0.1:22222; retrying. ...
```

These messages appear on state changes, not on every poll. A successful
connection is reported only when the live-link initialization succeeds;
disconnections are reported when detected on a subsequent poll. The gateway
retries automatically. `Updated <node>/<input>` means the gateway accepted data;
it does not mean ParaView is connected or has made an extract visible.

### Browser / WASM backend

The same node automatically uses HTTP when running inside the browser's Pyodide
Web Worker. Native Python continues to use binary TCP. Both transports share
gateway port **33333** and publish the same VTK data and node IDs.

Explicitly allow your editor's exact origin when starting the gateway:

```bash
/home/fbw/Apps/ParaView-6.2.0-MPI-Linux-Python3.12-x86_64/bin/pvpython --no-mpi \
  /home/fbw/repos/FlowGraph/FlowGraph/src/flowgraph/paraview_gateway.py \
  --allow-origin http://localhost:8082
```

Use the scheme, hostname and port from the editor address bar, with no path or
trailing slash. `http://127.0.0.1:8082` is a different origin from
`http://localhost:8082`. Repeat `--allow-origin` to allow additional trusted
origins. HTTP uploads are disabled by default; wildcard origins are not accepted.
Allowed origins must not contain carriage returns or line feeds. CORS responses
use the exact matching configured origin rather than echoing the request header.
Do not allow websites you do not trust to publish data to your local gateway.

After updating the Python code, rebuild the WASM wheel and web deployment with
`make build` in `/home/fbw/repos/FlowGraph/FlowGraph_web`, then reload the editor
to create a fresh worker. A gateway restart alone does not update Python code
already loaded in the browser. The production build uses the same command.

The browser POSTs a binary frame to `/api/v1/dataset`, with an explicit CORS
preflight. A synchronous XMLHttpRequest runs in the execution worker, not the UI
thread, preserving the node executor contract. Browser local-network permission
may be required. Browser mixed-content/local-network policies still apply;
the verified setup is the editor served locally over HTTP and a loopback gateway.
HTTPS-hosted editors may require additional browser permission or a trusted
HTTPS reverse proxy; this script does not terminate TLS.

Extract **FlowGraph outputs** from the Catalyst pipeline (the extract icon next
to the source), then run the workflow and enable the extract's visibility in
ParaView. Reset the camera after the first mesh upload. This persistent multiblock
source is registered before connection so uploads arriving afterward are visible.
Its named blocks contain the workflow node instance ID and input name, such as
`node_12/mesh` and `node_12/table`. Use Extract Block to select individual datasets;
use a Spreadsheet View or chart for tables.

One Send to ParaView node has three expandable input families: **Mesh**, **Table**,
and **Image**, with at most **10 inputs per type**. Connecting a slot exposes the
next numbered slot until the limit is reached (`mesh_1` through `mesh_10`, and
likewise for tables and images). Only connected inputs are sent. Each slot has a
distinct named block, such as
`node_12/mesh_1`, so repeated runs replace only that slot's dataset.
Saved connections to the former unnumbered or `*_extra_*` inputs must be
reconnected to the numbered inputs.
The gateway's default 128-dataset total limit still applies; increase
`--max-sources` if needed. Restart the gateway and reload the rebuilt browser
editor when upgrading to this feature.

Each bridge execution sends a node-scoped transaction: begin, datasets, then
commit. The gateway stages incoming data and publishes the complete new input
set only at commit, clearing that node's inputs omitted from the run. Other
bridge nodes are untouched. Disconnect an edge and **run the workflow again** to
remove its old data; running with no inputs clears all data for that bridge.
Editing edges alone does not notify the gateway. Failed/aborted transactions
preserve the previous data; abandoned transactions expire after 60 seconds of
inactivity. Staging is bounded to 256 MiB of serialized payload across active
transactions (in addition to the retained data), with one active transaction per
node. Overlapping executions of the same node are rejected. Existing blocks
keep their positions where possible; removed blocks are emptied and their slots
may be reused. Standalone legacy uploads remain immediate and do not prune.
Restart the gateway and reload the rebuilt editor to enable transaction support.

Multiple **Send to ParaView** nodes share the single **FlowGraph outputs**
pipeline entry; one entry does not mean only one node was received. Each distinct
node/input pair is a separate named block. For independent pipeline entries and
visibility controls, create an **Extract Block** filter for each desired block,
select its `node-id/mesh` (or other input) block and click **Apply**. Enable each
filter's visibility and reset the camera to include all meshes; hide the original
aggregate if you only want to display the filters. Updating one node replaces
only its own block, not another node's data. Coincident meshes can visually
overlap even when both are present.

The node ID is also attached as `flowgraph_workflow_node_id` field data, distinct
from mesh point IDs. Later executions replace the same named block's data. Existing
ParaView display/filter settings can therefore be reused.

Gateway options: `--host`, `--port`, `--paraview-host`, `--paraview-port`,
`--interval` (upload/control polling, default 0.2 seconds), `--live-interval`
(minimum gap between event-driven deliveries, default 1 second), and
`--max-sources` (default 128). Data is delivered on connection/reconnection,
accepted uploads, and live extract/pipeline changes, not on every poll. Idle
control polling does not resend images or advance the delivered timestep.
Slow deliveries receive an idle gap of at least twice their duration before
another pending delivery; control polling continues during this gap. Multiple
updates within the gap are coalesced to the latest state. Each delivery still
sends all active extracts, not just changed blocks. Image resolution is not
reduced. Stop with
Ctrl+C. This is a latest-state viewer, not timestep recording: the polling
delivery counter is not simulation time, and Catalyst pause/breakpoint controls are not
implemented. Different workflows with identical bridge node IDs share a source
when using the same gateway; use distinct IDs or separate gateway processes.

### Troubleshooting connections

If ParaView shows an old result after a disconnect/reconnect, upload `200` and
`Updated` messages only establish gateway acceptance, not that the visible
extract is receiving data. Test with a fresh ParaView window/session, restart the
gateway, connect Catalyst on 22222, extract **FlowGraph outputs** from the current
Catalyst connection, run the workflow and enable that fresh extract's visibility.
Reset the camera. Do not add Extract Block filters until the aggregate displays
the current data. Successful bridge transactions remove disconnected inputs for
that node. The gateway still retains blocks from earlier node IDs, including
renamed/deleted nodes, until it restarts; it receives no workflow-deletion events.
A reconnect alone does not clear those retained blocks. If a clean session still
shows stale geometry, collect a screenshot of the pipeline and Information tab
alongside both node-ID update messages; do not assume upload success proves
display refresh.

A `GET /` request is not a dataset upload. Opening the gateway address in a
browser now returns a small reachability response (also available at `/health`).
Older gateway processes return `501 Unsupported method ('GET')`; that alone
does not prove workflow delivery failed. If the request is a WebSocket upgrade,
the updated gateway returns 426 and logs a stale-worker hint. Rebuild/reload
the web runtime rather than using socket emulation. A successful current WASM
execution logs `POST /api/v1/dataset` and `Updated <node-id>/<input>`.

If the gateway reports an invalid header or a message size limit, do not assume
the mesh is too large: incompatible clients can be interpreted as binary lengths.
The updated warning identifies HTTP/WebSocket, unframed JSON, or TLS where possible,
and otherwise includes the declared lengths and header bytes. Restart the gateway
after updating the script to enable these diagnostics.

- Restart the workflow's Python process as well to load updated sender code;
  reloading a workflow JSON file does not reload imported Python modules.
- The node's gateway port is **33333**. ParaView uses **Catalyst → Connect** on
  **22222**, not the ordinary **Connect to Server** action.
- If the gateway still reports an HTTP/WebSocket request on a binary TCP port,
  it is running old gateway code. Restart it with `--allow-origin` for the editor,
  rebuild the web deployment, and reload the browser worker. WebSocket socket
  emulation is not used: the updated WASM sender uses the HTTP upload endpoint.
- A real oversized dataset is rejected by the current sender before connecting.
  The error includes its serialized size and the 256 MiB limit. Sender and gateway
  must use the same protocol and size limits.

### Data and transport limits

- Meshes are VTK projections of canonical Muscat data; nodal/element fields
  are preserved. Surface meshes are normalized to unstructured grids.
- Tables require equal-length numeric/boolean scalar or vector columns, or
  scalar string columns. Arbitrary objects, nulls and complex values are rejected.
  Booleans are sent as unsigned bytes.
- Pillow images become VTK image data, with vertical orientation corrected.
  Grayscale (including float/16-bit), RGB/RGBA and LA values are preserved;
  palette/bilevel images are expanded and other modes convert to RGB. This input
  does not accept ImageJ NumPy arrays or volumetric images.
  Empty images are rejected. The gateway logs image dimensions, extent, point/cell
  counts and pixel tuple/component counts on every accepted image. If ParaView
  reports zero points, compare these counts first: nonzero gateway counts mean
  the image arrived with pixels, but do not prove the selected display/filter
  received them. Include that log line and the selected block's Information tab
  when reporting an empty image; zero cells alone is not a sufficient pixel check.
  Browser images use explicit inline VTK XML with the actual image extent and
  base64 pixel bytes, bypassing a WASM VTK writer extent bug. This image payload
  is uncompressed (roughly four-thirds of raw pixel bytes); native writers retain
  compression. Reload the rebuilt editor to load this sender-side correction.
- Framed TCP messages (or the same frame in an HTTP body for WASM) carry bounded
  metadata and compressed VTK XML arrays;
  no pickle or shared filesystem is used. The maximum serialized dataset size
  is 256 MiB and metadata is limited to 16 KiB. Serialization necessarily allocates
  buffers; upstream values are not modified.
- Acknowledgement confirms gateway acceptance, **not** that ParaView rendered
  the data. Errors/timeouts fail the node visibly. Multiple inputs are sent
  separately, so a later failure does not roll back earlier accepted inputs.
- The receiver is sequential and has ten-second read/acceptance timeouts.
  Raising the node timeout does not raise receiver limits. On an ambiguous timeout,
  retrying updates the same source rather than adding another.
- Only expose this unauthenticated service to trusted local clients. Keep the
  loopback defaults; for remote use employ a trusted tunnel. Exact-origin checks
  limit browser access but are not authentication for native clients. No TLS,
  authentication, or hostile-input sandbox is provided. Retained data and user-created ParaView
  filters consume memory; restart to clear sources.