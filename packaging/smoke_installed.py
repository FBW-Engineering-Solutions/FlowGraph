"""Exercise installed core APIs, resources, persistence, and the CLI, without pytest."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import sysconfig
from importlib.metadata import distribution
from pathlib import Path


def smoke_test(version: str, source_root: Path) -> None:
    """Fail if imports escape the test environment or expected behavior changes."""
    from PIL import Image

    import flowgraph
    from flowgraph.adapters.simple_sources import SET_STRING
    from flowgraph.adapters.workflow_interfaces import WORKFLOW_OUTPUT
    from flowgraph.application.node_registry import create_node_registry
    from flowgraph.application.workflow_core import WorkflowEdge, WorkflowGraph
    from flowgraph.application.workflow_io import load_workflow, save_workflow
    from flowgraph.resources import package_resource_path

    installed = distribution("flowgraph")
    assert flowgraph.__version__ == installed.version == version
    for location in (Path(flowgraph.__file__), Path(installed.locate_file(""))):
        resolved = location.resolve()
        assert resolved.is_relative_to(Path(sys.prefix).resolve()), resolved
        assert not resolved.is_relative_to(source_root.resolve()), resolved
    print(f"Testing flowgraph {version} from {flowgraph.__file__}", flush=True)

    # Read actual packaged data, not just an existing directory.
    image_path = package_resource_path("testdata", "ColorCardboard.jpg")
    assert image_path.resolve().is_relative_to(Path(sys.prefix).resolve())
    with Image.open(image_path) as image:
        image.load()
        assert image.width > 0 and image.height > 0
    packaged_workflow = package_resource_path("testdata", "SimpleReadMesh.json")
    assert json.loads(packaged_workflow.read_text(encoding="utf-8"))

    registry = create_node_registry()
    graph = WorkflowGraph(
        [
            SET_STRING.create_instance("source", parameters={"value": "packaging-ok"}),
            WORKFLOW_OUTPUT.create_instance("output", parameters={"name": "result"}),
        ]
    )
    graph.add_edge(WorkflowEdge("source", "value", "output", "value"), registry)
    graph.sync_boundary_nodes(registry)
    path = save_workflow(graph, Path.cwd() / "smoke-workflow.json")
    assert (
        load_workflow(path, registry).require_node("source").parameters["value"] == "packaging-ok"
    )

    executable = Path(sysconfig.get_path("scripts")) / (
        "flowgraph.exe" if sys.platform == "win32" else "flowgraph"
    )
    subprocess.run([str(executable), "--help"], check=True)
    inspected = subprocess.run(
        [str(executable), "inspect", str(path)], check=True, capture_output=True, text=True
    )
    assert "result" in inspected.stdout, inspected.stdout
    output = Path.cwd() / "outputs.json"
    subprocess.run([str(executable), "run", str(path), "--json-output", str(output)], check=True)
    assert json.loads(output.read_text(encoding="utf-8")) == {"result": "packaging-ok"}
    print(
        "Installed resources, workflow round trip, CLI inspection and execution passed", flush=True
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    arguments = parser.parse_args()
    smoke_test(arguments.version, arguments.source_root)
