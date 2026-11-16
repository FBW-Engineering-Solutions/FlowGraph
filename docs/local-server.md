# Experimental local execution API

This is a prototype for trusted local clients, not an internet-facing service.
It uses Python's standard-library HTTP server and adds no HTTP dependencies.

The file content API downloads regular files unchanged and directories as compressed
ZIP archives (including nested and empty directories). Directory downloads respect
the server download size limit and exclude symlinks. Deleting a directory removes
its contents recursively; clients must request user confirmation first. Workspace
root paths and paths outside the workspace remain forbidden.

## Quick start

Create a workspace directory, then run from your core checkout:

```bash
uv run flowgraph serve --workspace /absolute/path/to/workspace
```

The server binds only to `127.0.0.1` and prints its address, a new bearer token,
and an **Open editor** link. Open that link to connect the public editor at
`https://flowgraph-web.fbw-es.com` to Local Python server automatically. Approve
browser local/loopback access if requested.

For manual connection, select **Run → Python backend → Local Python server**
and enter the printed token and port (default `8765`). Keep the token and launch
link private. The link carries `#token=...&port=...`; the public editor removes
these credentials from the address bar and keeps them in memory. After reloading
the editor or restarting the server, use the current launch link again.

Stop the server with **Ctrl+C**; shutdown terminates active execution.

Add `--verbose` (or `-v`) to print startup/shutdown state, the resolved workspace,
allowed editor origins, execution/request/result limits, sanitized HTTP endpoints
and response codes, execution state transitions, and labeled node output-port
summaries to stderr. Worker stdout (including `print()`) and stderr (including
logs and tracebacks) are also forwarded to the console without Python buffering.
This applies to one-shot executions and persistent sessions. For example:

```bash
uvx --with imagej flowgraph serve --workspace . --verbose
```

Execution transitions include running, completed, failed, cancelled, and advisory
timeout warnings; polling does not repeat transition messages. HTTP polling requests are
still logged. HTTP diagnostics omit credentials, query values, request bodies,
and arbitrary request paths. **Node messages and output values can contain sensitive
workflow data or credentials; keep verbose console logs private.** Output-port
summaries are bounded and use the existing serialized results, without copying
runtime data or dumping full arrays, meshes, or images. Each received node result
is logged once, including reused session results; polling does not repeat it.
The usual token and launch link remain on stdout; keep them private. Without the
flag, additional diagnostics are disabled and worker stdout/stderr are discarded.

Core serves only the API, not editor assets: `/` and other non-API paths return
404. The public editor, a separately served editor, or FlowGraph Desktop supplies
the UI. Starting this server does not change standalone WASM deployments.

### Recovering editor state

The runtime advertises `executionRecovery: 1`. Authenticated
`GET /api/v1/execution-state` returns `{workflow, options, previous_result, job}`
for the active execution, or the most recently submitted job when idle. `job`
includes current progress, all retained live node results and their cursor, and
the final result when available. Clients resume polling the returned job ID;
recovery never submits a new execution or stops a worker. `previous_result` is
an optional display baseline for selected-node runs with an unchanged workflow
and session; it is not proof that runtime objects are still cached.

The web editor exposes this through **Retrieve current state from server** before
**Use backend**. This replaces the local workflow, not merges it. State belongs
to the server, not an individual browser: all authorized clients can retrieve
the active/latest submission. Only submitted workflows are known to the server;
later editor changes are not recovered. Records are bounded to 32 jobs in memory
and lost at server shutdown. Session-worker expiration, cancellation and eviction
may discard computation caches independently of retained serialized previews.
An empty or restarted server returns 404 until another execution is submitted.

## Other clients

### Custom Python nodes

Configure trusted Python-file plugins at startup:

```bash
uv run flowgraph serve --workspace /absolute/path/to/workspace \
  --plugin /absolute/path/to/custom_nodes.py
```

Repeat `--plugin` for several files. Each exports `AVAILABLE_NODES`, an iterable
of `NodeDefinition` objects. The server validates definitions before listening,
includes plugin nodes in `/api/v1/catalog`, and loads them in both one-shot and
persistent session workers. Relative paths resolve against the launch directory,
not the workspace. Restart after changes, and keep files unchanged while serving.

Plugin imports execute trusted Python with your permissions; dependencies must
already be installed. There is no HTTP plugin-upload/loading endpoint, and
workflows cannot select plugin files. Standalone browser WASM and Desktop's
local registry are unchanged. See the [custom-node guide](../doc/user-guide/custom-nodes.md)
for a complete file example and Python APIs.

### Client origins

For a separately hosted editor, pass its origin with `--allow-origin`. For example,
the local editor started by `make serve-serial` uses:

```bash
uv run flowgraph serve --workspace /absolute/path/to/workspace \
  --allow-origin http://127.0.0.1:8082
```

For FlowGraph Desktop, allow its client origin and enter core's address and token
in Desktop. Managed desktop launches pass the origin automatically.

Origin rules:

- Repeat `--allow-origin` to allow multiple clients. Explicit values **replace**
  the default public editor origin. The printed launch link uses the first value.
- Use HTTPS, or HTTP on `127.0.0.1`, `localhost`, or `[::1]` for local clients.
- Match the browser's scheme, host and port exactly, with no path, credentials,
  or trailing slash. Omit the default HTTPS port `:443`.
- An origin covers the whole website, not just an editor path. Trust all scripts
  served there; no wildcard origins are allowed.

Browser local-access permission is separate from CORS and cannot be bypassed by
the server. Browser/OS compatibility requires deployment testing. When constructing
`LocalServer` directly, no external origins are allowed by default; the CLI adds
the public editor default.

## Server options

| Option | Default | Purpose |
| --- | --- | --- |
| `--workspace` | Required | Existing directory for workflow execution and file operations |
| `--plugin FILE.py` | None | Trusted Python node definitions; repeatable, loaded at startup and in workers |
| `--port` | `8765` | Loopback API port; `0` selects an available port |
| `--allow-origin` | Public editor origin | Allowed client origin; repeatable as described above |
| `--execution-timeout` | `120` | Default advisory execution timeout in seconds; does not kill the worker |
| `--max-request-bytes` | `16777216` (16 MiB) | Maximum request body size |
| `--verbose`, `-v` | Off | Print server state and sanitized activity to stderr |

## API version 1

### Authentication and requests

Every API endpoint requires `Authorization: Bearer TOKEN`; tokens are not accepted
in query strings. The Host header must match the printed server address. Browser
origins must match that address or an allowed client origin. Allowed clients receive
restricted CORS preflights; actual requests still require the token. Other
cross-site requests are rejected. Responses are not cached. There is no browser
login, cookie authentication, or unauthenticated health endpoint.

All JSON requests use `Content-Type: application/json`. Requests with a body must
include one Content-Length; chunked transfer encoding is unsupported. Empty POST
requests (cancel/demo) use Content-Length 0. File uploads/downloads are raw bytes.

### Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/runtime` | Protocol, workflow-format version, capabilities, installed packages/versions, workspace and limits |
| GET | `/api/v1/catalog` | Metadata-only catalog from this installed core |
| GET | `/api/v1/execution-state` | Authenticated active/latest submission: workflow, options, previous selected-run result and current job; 404 if none retained |
| POST | `/api/v1/executions` | Submit `{"workflow": { ...workflow document... }}`; returns HTTP 202 and a job |
| GET | `/api/v1/executions/{id}` | Get job state and result |
| POST | `/api/v1/executions/{id}/cancel` | Cancel a running job; terminal jobs are unchanged |
| GET | `/api/v1/files` | List workspace files and directories |
| GET | `/api/v1/files/content?path=relative/path` | Download a file |
| PUT | `/api/v1/files/content?path=relative/path` | Upload/replace a file; missing parents are created |
| DELETE | `/api/v1/files/content?path=relative/path` | Delete a file |
| POST | `/api/v1/files/demo` | Copy five packaged demo assets; refuses existing destination files |

### Execution lifecycle

A job has `id`, `state`, `result`, `error`, `timed_out`, and `timeout_seconds`. States are `running`, `completed`,
`failed`, and `cancelled`. The unchanged `execute_workflow_json()` response is
nested under `result`; workflow validation/node errors make a job `failed` and
remain available there. Process failures have an `error` message.
Submission accepts an optional top-level `timeout_seconds` (finite positive number,
at most 86400), independent of incremental execution `options`. If omitted, the
server's `--execution-timeout` is used. Runtime metadata advertises
`advisoryExecutionTimeout: 1`. At the threshold, `timed_out` becomes true but the
job stays `running`, retains its worker/cache and admission slot, and can still
complete successfully. Use the cancellation endpoint to explicitly terminate the
worker; the HTTP server remains available. HTTP request timeouts are separate.
Cancelled jobs have no execution result. Unknown/expired jobs return HTTP 404.
Concurrent submission returns HTTP 409. Only the 32 most recent jobs are retained,
in memory; restarting the server discards all jobs. Results are limited to 64 MiB
when read by the parent process. A fresh interpreter is launched per execution;
library startup is consequently paid on every run.

Example (substitute the printed token):

```bash
curl --header 'Authorization: Bearer TOKEN' http://127.0.0.1:8765/api/v1/runtime
curl --header 'Authorization: Bearer TOKEN' \
  --header 'Content-Type: application/json' \
  --data '{"workflow":{"format":"flowgraph-workflow","version":3,"nodes":[],"edges":[],"inputs":[],"outputs":[]}}' \
  http://127.0.0.1:8765/api/v1/executions
```

Poll the returned job ID to retrieve its result. The native web backend handles
this polling and uses the installed core's catalog.

## Security and prototype limitations

- **Native Python is not sandboxed.** Run only workflows you trust, with the same
  care as a local Python script. User functions can access files, environment
  variables, network resources, and processes permitted to your OS user.
- Each worker runs with the workspace as its current directory. File endpoints
  accept only workspace-relative paths and reject traversal, symlinks and special
  files. Directory mounting is not supported. These checks do not protect against
  a trusted workflow or another local process concurrently replacing directories
  (filesystem check/use races). Hard-linked files are not isolated either.
- Explicit cancellation or service shutdown terminates the direct workflow process, escalating to kill
  after two seconds. Processes deliberately spawned by workflow code are not
  managed or guaranteed to stop. Already-written files are not rolled back.
  Execution timeout alone does not terminate the process or limit resource usage.
- Runtime packages are reported from installed distribution metadata, not a promise
  that external tools, licenses, or optional native integrations are usable.
- Request/download limits and retained-job bounds are guardrails, not resource
  isolation: CPU, memory, disk usage, thread count and serialization size before
  result collection are not sandboxed or strictly bounded.
- No TLS, remote hosting, persistence, resumable uploads, or logs streaming is
  provided. Do not expose this server through a proxy or public port. GUI clients
  must serve their assets separately and allow only trusted scripts on their origin.