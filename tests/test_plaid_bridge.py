from pathlib import Path
from types import SimpleNamespace

from Muscat.Bridges.CGNSBridge import MeshToCGNS
from Muscat.TestData import GetTestDataPath

from flowgraph.adapters import ADAPTERS
from flowgraph.adapters.plaid_bridge import (
    EXTRACT_PLAID_INFO,
    EXTRACT_PLAID_SAMPLE,
    EXTRACT_PLAID_TIME_STEP,
    LOAD_PLAID_DATASET,
)
from flowgraph.adapters.readers import LOAD_MUSCAT
from flowgraph.application.workflow_core import (
    DataType,
    NodeDefinition,
    NodeInstance,
    NodeRegistry,
    PortDefinition,
    PortDirection,
    WorkflowEdge,
    WorkflowExecutor,
    WorkflowGraph,
)


def test_plaid_node_exports_requested_typed_ports() -> None:
    assert [(port.name, port.data_type.id) for port in EXTRACT_PLAID_SAMPLE.inputs] == [
        ("dataset", "plaid-dataset"),
        ("infos", "plaid-info"),
        ("split", "string"),
        ("sample_number", "integer"),
    ]


def test_plaid_node_is_registered_under_external_tools() -> None:
    external_tools = next(group for group in ADAPTERS.groups if group.label == "External Tools")
    plaid = next(group for group in external_tools.subgroups if group.label == "Plaid")

    assert plaid.node_definitions == (
        LOAD_PLAID_DATASET,
        EXTRACT_PLAID_SAMPLE,
        EXTRACT_PLAID_TIME_STEP,
        EXTRACT_PLAID_INFO,
    )
    assert ADAPTERS.require("extract-plaid-time-step") is EXTRACT_PLAID_TIME_STEP


def test_plaid_nodes_keep_their_icons_without_optional_dependency() -> None:
    external_tools = next(group for group in ADAPTERS.groups if group.label == "External Tools")
    plaid = next(group for group in external_tools.subgroups if group.label == "Plaid")

    assert [definition.icon for definition in plaid.node_definitions] == [
        "mdi-database-arrow-down-outline",
        "mdi-database-search-outline",
        "mdi-calendar-clock-outline",
        "mdi-information-outline",
    ]


def test_extract_plaid_time_step_exports_typed_ports() -> None:
    assert [(port.name, port.data_type.id) for port in EXTRACT_PLAID_TIME_STEP.inputs] == [
        ("sample", "plaid-dataset"),
        ("time", "float"),
    ]
    assert [(port.name, port.data_type.id) for port in EXTRACT_PLAID_TIME_STEP.outputs] == [
        ("mesh", "mesh-document"),
    ]


def test_extract_plaid_info_exports_all_top_level_attributes() -> None:
    assert [port.name for port in EXTRACT_PLAID_INFO.inputs] == ["infos"]
    assert [port.name for port in EXTRACT_PLAID_INFO.outputs] == [
        "owner",
        "license",
        "data_production",
        "data_description",
        "num_samples",
        "storage_backend",
    ]

    data_production = object()
    infos = SimpleNamespace(
        owner="FlowGraph",
        license="MIT",
        data_production=data_production,
        data_description="A test dataset",
        num_samples={"train": 4, "test": 2},
        storage_backend="zarr",
    )

    result = EXTRACT_PLAID_INFO.executor({"infos": infos}, {})

    assert result == {
        "owner": "FlowGraph",
        "license": "MIT",
        "data_production": data_production,
        "data_description": "A test dataset",
        "num_samples": {"train": 4, "test": 2},
        "storage_backend": "zarr",
    }


def test_extract_plaid_info_accepts_missing_optional_attributes() -> None:
    infos = SimpleNamespace(
        owner="FlowGraph",
        license="MIT",
        data_production=None,
        data_description=None,
        num_samples=None,
        storage_backend=None,
    )
    info_type = DataType("infos", "Infos", object)
    source = NodeDefinition(
        id="source",
        icon="",
        label="Source",
        ports=(PortDefinition("infos", PortDirection.OUTPUT, info_type),),
        executor=lambda _inputs, _parameters: {"infos": infos},
    )
    registry = NodeRegistry()
    registry.register(source)
    registry.register(EXTRACT_PLAID_INFO)
    graph = WorkflowGraph(
        [NodeInstance("source", "source"), NodeInstance("extract", EXTRACT_PLAID_INFO.id)]
    )
    graph.add_edge(WorkflowEdge("source", "infos", "extract", "infos"), registry)

    result = WorkflowExecutor(registry).run(graph)

    assert result.node_outputs["extract"]["data_description"] is None
    assert result.node_outputs["extract"]["num_samples"] is None


class _FakePlaidSample:
    def __init__(self, tree: list) -> None:
        self.tree = tree
        self.requested: tuple[float, bool] | None = None

    def get_tree(self, *, time: float, only_mesh: bool) -> list:
        self.requested = (time, only_mesh)
        return self.tree


def test_extract_plaid_time_step_converts_tree_to_mesh_document() -> None:
    source = Path(GetTestDataPath()) / "square2D.mesh"
    document = LOAD_MUSCAT.executor({"path": source}, {})["mesh"]
    sample = _FakePlaidSample(MeshToCGNS(document.mesh))

    result = EXTRACT_PLAID_TIME_STEP.executor({"sample": sample}, {"time": 2.5})

    assert sample.requested == (2.5, False)
    assert result["mesh"].mesh.GetNumberOfNodes() == document.mesh.GetNumberOfNodes()
    assert result["mesh"].mesh.GetNumberOfElements() == document.mesh.GetNumberOfElements()


class _FakeConverter:
    def to_plaid(self, dataset: object, index: int) -> tuple[object, int]:
        return dataset, index


def test_extract_plaid_sample_uses_split_converter() -> None:
    result = EXTRACT_PLAID_SAMPLE.executor(
        {
            "dataset": ({"train": ["raw"]}, {"train": _FakeConverter()}),
            "infos": object(),
        },
        {"split": "train", "sample_number": 3},
    )

    assert result == {"sample": (["raw"], 3)}
