# Workflow JSON format

FlowGraph workflow files are UTF-8 JSON objects with the format identifier
`flowgraph-workflow`. The current format version is `2`.

## Top-level structure

```json
{
  "format": "flowgraph-workflow",
  "version": 2,
  "nodes": [],
  "inputs": [],
  "outputs": [],
  "edges": []
}
```

Each node has a stable instance `id`, a registry `definition_id`, a JSON object
of `parameters`, and an optional `{ "x": number, "y": number }` position. A
composite node may contain a recursively serialized `subworkflow`.

For `user-function` nodes, `parameters.code` may be a JSON string with escaped
newlines (legacy form) or an array of Python source lines. New exports use an
array; the loader joins its entries with `\n` before parsing the function. An
empty first or last entry preserves a leading or trailing newline, and empty
entries between lines preserve blank lines. For example:

```json
"code": ["def Execute(value) -> tuple[Any]:", "    return (value,)", ""]
```

Each array entry must be a string without embedded newlines. In memory, code
remains a single Python source string. Other parameters retain their existing
JSON representations.

Edges refer to named ports using `source_node`, `source_port`, `target_node`,
and `target_port`. Workflow boundary inputs and outputs refer to a node and
port through `name`, `node_id`, and `node_port`.

## Compatibility behavior

The loader rejects a missing or unknown format identifier, unsupported versions,
unknown node definitions, malformed coordinates, invalid endpoints, duplicate
inputs, incompatible connections, and cycles. It does not deserialize Python
objects or execute code while parsing.

Version `1` is accepted only for the legacy nested-workflow representation and
is normalized in memory to the current model. New files are always written as
version `2`. Unknown node parameters are retained by the parser but are subject
to node validation before execution; applications should not depend on unknown
fields being executable.

The format is not a general forward-compatibility guarantee during the alpha
series. Applications should preserve the original file and pin FlowGraph when
reproducible execution matters. Intentional compatibility breaks require a
changelog entry and migration guidance.

## Paths and capabilities

Relative paths resolve from the executing process working directory. The
`{testdata}` token identifies packaged FlowGraph fixtures. Remote downloads,
local file access, external tools, and the trusted user-function node are
explicit capabilities and should not be enabled for untrusted workflows.