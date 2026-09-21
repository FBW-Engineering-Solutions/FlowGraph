"""Nodes for documentation and grouping ."""

from flowgraph.adapters.data_types import STRING
from flowgraph.application.workflow_core import NodeDefinition, ParameterDefinition

DOC_TITLE = NodeDefinition(
    id="title-doc",
    icon="",
    label="Title",
    description="Just a Title",
    ports=(),
    executor=lambda x, y: None,
    parameters=(
        ParameterDefinition(
            name="title",
            kind=STRING,
            label="Title",
            default="Title",
            port=False,
        ),
    ),
    presentation="title",
)

DOC_PARAGRAPH = NodeDefinition(
    id="paragraph-doc",
    icon="",
    label="Paragraph",
    description="Long-form documentation text",
    ports=(),
    executor=lambda x, y: None,
    parameters=(
        ParameterDefinition(
            name="text",
            kind=STRING,
            label="Text",
            default="Write documentation here.",
            port=False,
        ),
    ),
    presentation="paragraph",
)


AVAILABLE_NODES = (DOC_TITLE, DOC_PARAGRAPH)
