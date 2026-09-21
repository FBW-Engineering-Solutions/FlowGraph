from pathlib import Path

from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_io import execute_workflow, load_workflow

registry = create_node_registry()
my_workflow = load_workflow(
    Path(__file__).parent / ".." / "testdata" / "workflowtest.json", registry
)

print(my_workflow)

for node in my_workflow.nodes:
    node.pprint()


parameter_overrides = {"create-muscat-element-filter-2": {"dimensionality": [0]}}

result = execute_workflow(my_workflow, registry=registry, parameter_overrides=parameter_overrides)

print(result.node_outputs["filter-mesh-muscat-2"]["mesh"].mesh)
