from flowgraph.adapters.data_types import TABLE_DOCUMENT
from flowgraph.adapters.sinks import PLOT_TABLE, TO_3D_VIEW


def test_plot_table_declares_only_a_table_input() -> None:
    assert PLOT_TABLE.label == "Show Table"
    assert PLOT_TABLE.presentation == "plot-table"
    assert PLOT_TABLE.outputs == ()
    assert [(port.name, port.data_type, port.required) for port in PLOT_TABLE.inputs] == [
        ("table", TABLE_DOCUMENT, True),
    ]
    assert [port.name for port in PLOT_TABLE.ports] == ["table"]


def test_display_labels_keep_existing_definition_ids() -> None:
    assert TO_3D_VIEW.label == "Show Mesh"
    assert TO_3D_VIEW.id == "mesh-sink"
    assert PLOT_TABLE.id == "plot-table"
