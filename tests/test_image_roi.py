"""ROI coordinates remain usable without an image or presentation dependencies."""

import json

import pytest
from PIL import Image

from flowgraph.adapters import ADAPTERS
from flowgraph.adapters.data_types import VEC2D
from flowgraph.adapters.sinks import LINE_OF_INTEREST, REGION_OF_INTEREST, SHOW_IMAGE
from flowgraph.application.node_registry import create_node_registry
from flowgraph.application.workflow_core import PortDirection, WorkflowGraph
from flowgraph.application.workflow_execution import _display_images, execute_workflow_json
from flowgraph.application.workflow_io import workflow_from_dict, workflow_to_dict


def test_roi_catalog_position_and_contract():
    definitions = ADAPTERS.node_definitions
    assert definitions[definitions.index(SHOW_IMAGE) + 1] is REGION_OF_INTEREST
    assert definitions[definitions.index(REGION_OF_INTEREST) + 1] is LINE_OF_INTEREST
    assert [
        (p.name, p.required) for p in REGION_OF_INTEREST.ports if p.direction is PortDirection.INPUT
    ] == [("input", False)]
    assert REGION_OF_INTEREST.ports[1].data_type.id == "any"
    assert all(p.kind.id == "VEC2DI" and not p.port for p in REGION_OF_INTEREST.parameters[:2])
    assert LINE_OF_INTEREST.ports[0].required is False
    assert LINE_OF_INTEREST.ports[1].name == "loi"
    assert LINE_OF_INTEREST.ports[1].data_type.id == "any"
    assert all(p.kind.id == "VEC2DI" and not p.port for p in LINE_OF_INTEREST.parameters[:2])
    for definition in (REGION_OF_INTEREST, LINE_OF_INTEREST):
        parameter = definition.parameters[2]
        assert parameter.name == "negate_y"
        assert parameter.kind.id == "boolean"
        assert parameter.default is False
        assert not parameter.port


@pytest.mark.parametrize(
    "definition,port", [(REGION_OF_INTEREST, "roi"), (LINE_OF_INTEREST, "loi")]
)
@pytest.mark.parametrize("corners", [([0, 0], [0, 0]), ([10, 20], [90, 50]), ([90, -50], [-2, 3])])
@pytest.mark.parametrize("negate_y", [False, True])
def test_roi_immutable_output_and_persistence_without_image(corners, definition, port, negate_y):
    parameters = dict(zip(("corner1", "corner2"), corners))
    parameters["negate_y"] = negate_y
    node = definition.create_instance("roi", parameters=parameters)
    expected = [(x, -y if negate_y else y) for x, y in corners]
    outputs = definition.executor({}, node.parameters)
    output = outputs[port]
    assert output == tuple(expected)
    assert node.parameters["corner1"] == corners[0]
    assert node.parameters["corner2"] == corners[1]
    assert isinstance(output, tuple) and all(isinstance(corner, tuple) for corner in output)
    for index, name in enumerate(("point1", "point2")):
        assert outputs[name] == [float(component) for component in expected[index]]
        assert VEC2D.accepts(outputs[name])
        assert definition.output(name).data_type is VEC2D
    registry = create_node_registry()
    payload = workflow_to_dict(WorkflowGraph([node]))
    restored = workflow_from_dict(json.loads(json.dumps(payload)), registry)
    assert restored.require_node("roi").parameters == node.parameters
    response = json.loads(execute_workflow_json(json.dumps(payload)))
    assert response["status"] == "ok"
    assert response["display_images"] == {}
    assert response["nodes"]["outputs"]["roi"][port] == [list(corner) for corner in expected]
    assert response["nodes"]["outputs"]["roi"]["point1"] == list(expected[0])
    assert response["nodes"]["outputs"]["roi"]["point2"] == list(expected[1])


@pytest.mark.parametrize("definition", [REGION_OF_INTEREST, LINE_OF_INTEREST])
@pytest.mark.parametrize("corner", [[1], [1, 2, 3], [1.5, 2], [True, 2]])
def test_roi_rejects_invalid_corner_shape_or_components(corner, definition):
    with pytest.raises(ValueError, match="exactly two integers"):
        definition.executor({}, {"corner1": corner, "corner2": [0, 0]})


@pytest.mark.parametrize(
    "definition,port", [(REGION_OF_INTEREST, "roi"), (LINE_OF_INTEREST, "loi")]
)
@pytest.mark.parametrize("negate_y", [False, True])
def test_roi_optional_image_is_previewed_without_modification(definition, port, negate_y):
    image = Image.new("RGBA", (20, 10), (10, 20, 30, 40))
    pixels = image.tobytes()
    node = definition.create_instance(
        "roi", parameters={"corner1": [2, 3], "corner2": [10, 8], "negate_y": negate_y}
    )
    sign = -1 if negate_y else 1
    assert definition.executor({"input": image}, node.parameters) == {
        port: ((2, sign * 3), (10, sign * 8)),
        "point1": [2.0, float(sign * 3)],
        "point2": [10.0, float(sign * 8)],
    }
    previews = _display_images(WorkflowGraph([node]), {"roi": {"input": image}})
    assert previews["roi"]["input"]["width"] == 20
    assert image.tobytes() == pixels
