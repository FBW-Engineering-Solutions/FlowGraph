from flowgraph.adapters.data_types import TABLE_DOCUMENT
from flowgraph.adapters.sinks import PLOT_TABLE


def test_plot_table_declares_only_a_table_input() -> None:
    assert PLOT_TABLE.label == "Plot Table"
    assert PLOT_TABLE.presentation == "plot-table"
    assert PLOT_TABLE.outputs == ()
    assert [(port.name, port.data_type, port.required) for port in PLOT_TABLE.inputs] == [
        ("table", TABLE_DOCUMENT, True),
    ]
    assert [port.name for port in PLOT_TABLE.ports] == ["table"]