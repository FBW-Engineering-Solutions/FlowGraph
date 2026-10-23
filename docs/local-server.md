# Experimental local execution API

This is a prototype for trusted local clients, not an internet-facing service.
It uses Python's standard-library HTTP server and adds no HTTP dependencies.
The web editor HTTP adapter and static editor hosting are not implemented here.
Existing WASM deployments are unchanged.

## Start

Create a workspace directory, then run from your core checkout:

```bash
uv run flowgraph serve --workspace /absolute/path/to/workspace --port 8765
```

The workspace must exist. The server binds only to `127.0.0.1` and prints its
address and a freshly generated bearer token. Keep that token private. Stop with
Ctrl+C; active execution is terminated during shutdown. Port `0` selects an
available port. `--execution-timeout` defaults to 120 seconds, and
`--max-request-bytes` defaults to 16777216 bytes (16 MiB).

Every endpoint requires `Authorization: Bearer TOKEN`. The Host header must match
the printed address exactly. If Origin is supplied, it must match that address;
cross-site requests are rejected and no CORS permissions are granted. Tokens are
not accepted in query strings. Responses are not cached. There is no unauthenticated
health endpoint, browser login, or cookie authentication.

## API version 1

All JSON requests use `Content-Type: application/json`. Requests with a body must
include one Content-Length; chunked transfer encoding is unsupported. Empty POST
requests (cancel/demo) use Content-Length 0. File uploads/downloads are raw bytes.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/runtime` | Protocol, workflow-format version, capabilities, installed packages/versions, workspace and limits |
| GET | `/api/v1/catalog` | Metadata-only catalog from this installed core |
| POST | `/api/v1/executions` | Submit `{"workflow": { ...workflow document... }}`; returns HTTP 202 and a job |
| GET | `/api/v1/executions/{id}` | Get job state and result |
| POST | `/api/v1/executions/{id}/cancel` | Cancel a running job; terminal jobs are unchanged |
| GET | `/api/v1/files` | List workspace files and directories |
| GET | `/api/v1/files/content?path=relative/path` | Download a file |
| PUT | `/api/v1/files/content?path=relative/path` | Upload/replace a file; missing parents are created |
| DELETE | `/api/v1/files/content?path=relative/path` | Delete a file |
| POST | `/api/v1/files/demo` | Copy five packaged demo assets; refuses existing destination files |

A job has `id`, `state`, `result`, and `error`. States are `running`, `completed`,
`failed`, and `cancelled`. The unchanged `execute_workflow_json()` response is
nested under `result`; workflow validation/node errors make a job `failed` and
remain available there. Process failures/timeouts have an `error` message.
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

Poll the returned job ID to retrieve its result. The API is ready for scripted
clients, but the web GUI still selects its WASM backend until a separate HTTP
adapter and same-origin local-editor deployment are added.

## Security and prototype limitations

- **Native Python is not sandboxed.** Run only workflows you trust, with the same
  care as a local Python script. User functions can access files, environment
  variables, network resources, and processes permitted to your OS user.
- Each worker runs with the workspace as its current directory. File endpoints
  accept only workspace-relative paths and reject traversal, symlinks and special
  files. Directory mounting is not supported. These checks do not protect against
  a trusted workflow or another local process concurrently replacing directories
  (filesystem check/use races). Hard-linked files are not isolated either.
- Cancellation/timeout terminates the direct workflow process, escalating to kill
  after two seconds. Processes deliberately spawned by workflow code are not
  managed or guaranteed to stop. Already-written files are not rolled back.
- Runtime packages are reported from installed distribution metadata, not a promise
  that external tools, licenses, or optional native integrations are usable.
- Request/download limits and retained-job bounds are guardrails, not resource
  isolation: CPU, memory, disk usage, thread count and serialization size before
  result collection are not sandboxed or strictly bounded.
- No TLS, remote hosting, persistence, resumable uploads, logs streaming, or editor
  hosting is provided. Do not expose this server through a proxy or public port.