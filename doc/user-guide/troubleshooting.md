---
id: user-guide.troubleshooting
title: Troubleshooting
section: User Guide
order: 40
---

# Troubleshooting

If a workflow node fails, inspect its parameters and the connected input data.

1. Confirm the input path exists.
2. Run the upstream nodes.
3. Review the node error message.

## Desktop mode under WSL

If desktop startup prints `MESA: error: ZINK: failed to choose pdev` or creates only a
Linux taskbar icon, close WSL and update WSLg from Windows PowerShell:

```powershell
wsl --shutdown
wsl --update
```

Reopen the Linux distribution and retry FlowGraph. If plain GTK windows also fail to
appear, the problem is in the current WSLg host session rather than FlowGraph.

You can always use browser mode, which runs the same loopback-only application:

```bash
uvx --from "flowgraph @ git+https://github.com/FBW-Engineering-Solutions/FlowGraph.git" flowgraph
```

Return to the [documentation home](../index.md).