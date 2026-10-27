import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
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
    assert [(port.name, port.data_type.id) for port in LOAD_PLAID_DATASET.outputs] == [
        ("dataset", "plaid-dataset"),
        ("infos", "plaid-info"),
        ("splits", "list[str]"),
    ]
    assert [(port.name, port.data_type.id) for port in EXTRACT_PLAID_SAMPLE.inputs] == [
        ("dataset", "plaid-dataset"),
        ("infos", "plaid-info"),
        ("split", "string"),
        ("sample_number", "integer"),
    ]
    assert [(port.name, port.data_type.id) for port in EXTRACT_PLAID_SAMPLE.outputs] == [
        ("sample", "plaid-sample"),
        ("timesteps", "list[float]"),
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
        ("sample", "plaid-sample"),
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
    def __init__(self, sample: object) -> None:
        self.sample = sample
        self.requested: tuple[object, int] | None = None

    def to_plaid(self, dataset: object, index: int) -> object:
        self.requested = (dataset, index)
        return self.sample


@pytest.mark.parametrize("times", [[], [0.0, 2.5], [0, 2], (0, 2.5), np.array([0, 2.5])])
def test_extract_plaid_sample_uses_split_converter(times) -> None:
    sample = SimpleNamespace(get_all_time_values=lambda: times)
    converter = _FakeConverter(sample)
    dataset = ["raw"]
    result = EXTRACT_PLAID_SAMPLE.executor(
        {
            "dataset": ({"train": dataset}, {"train": converter}),
            "infos": object(),
        },
        {"split": "train", "sample_number": 3},
    )

    assert converter.requested == (dataset, 3)
    assert result == {"sample": sample, "timesteps": [float(time) for time in times]}
    assert all(type(time) is float for time in result["timesteps"])


@pytest.mark.parametrize("splits", [[], ["train", "test"]])
def test_load_plaid_dataset_exposes_split_names(monkeypatch, splits) -> None:
    datasets = dict.fromkeys(splits)
    converters = dict.fromkeys(splits)
    infos = object()
    calls = []

    def load_infos(path):
        calls.append(("infos", path))
        return infos

    def load_dataset(path):
        calls.append(("dataset", path))
        return datasets, converters

    monkeypatch.setitem(sys.modules, "plaid", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "plaid.storage", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "plaid.storage.reader",
        SimpleNamespace(load_infos_from_disk=load_infos, init_from_disk=load_dataset),
    )

    result = LOAD_PLAID_DATASET.executor({}, {"path": "/data/plaid"})

    assert result == {"dataset": (datasets, converters), "infos": infos, "splits": splits}
    assert calls == [("infos", "/data/plaid"), ("dataset", "/data/plaid")]


@pytest.mark.parametrize(
    "sample",
    [
        object(),
        SimpleNamespace(get_all_time_values=lambda: None),
        SimpleNamespace(get_all_time_values=lambda: ["invalid"]),
    ],
)
def test_extract_plaid_sample_reports_time_value_errors_with_context(sample) -> None:
    with pytest.raises(ValueError, match="split='train', sample_number=3") as error:
        EXTRACT_PLAID_SAMPLE.executor(
            {"dataset": ({"train": []}, {"train": _FakeConverter(sample)}), "infos": object()},
            {"split": "train", "sample_number": 3},
        )
    assert error.value.__cause__ is not None


def test_plaid_sample_workflow_validates_typed_time_values() -> None:
    sample = SimpleNamespace(get_all_time_values=lambda: np.array([0, 2]))
    source = NodeDefinition(
        id="source",
        icon="",
        label="Source",
        ports=LOAD_PLAID_DATASET.outputs,
        executor=lambda _inputs, _parameters: {
            "dataset": ({"train": []}, {"train": _FakeConverter(sample)}),
            "infos": object(),
            "splits": ["train"],
        },
    )
    registry = NodeRegistry()
    registry.register(source)
    registry.register(EXTRACT_PLAID_SAMPLE)
    graph = WorkflowGraph(
        [
            source.create_instance("source"),
            EXTRACT_PLAID_SAMPLE.create_instance("extract", parameters={"split": "train"}),
        ]
    )
    for name in ("dataset", "infos"):
        graph.add_edge(WorkflowEdge("source", name, "extract", name), registry)

    result = WorkflowExecutor(registry).run(graph)

    assert result.node_outputs["extract"] == {"sample": sample, "timesteps": [0.0, 2.0]}
