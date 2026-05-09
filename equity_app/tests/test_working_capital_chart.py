"""
ui/charts/cash_conversion_cycle.py — slim figure builder tests.

The `compute_ccc_history` engine itself is exercised via the existing
`analyze_ccc()` flow elsewhere; here we verify the figure-only path
that powers the Charts tab.
"""
from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go

from ui.charts.cash_conversion_cycle import (
    build_ccc_chart, build_ccc_breakdown_table,
)


def _sample_data():
    periods = pd.date_range("2018", periods=5, freq="YE")
    income = pd.DataFrame({
        "revenue":       [100, 110, 121, 132, 145],
        "costOfRevenue": [60, 66, 73, 80, 88],
    }, index=periods)
    balance = pd.DataFrame({
        "netReceivables":           [10, 11, 12, 13, 14],
        "inventory":                [5, 5, 6, 6, 7],
        "accountPayables":          [12, 13, 14, 15, 16],
        "totalCurrentLiabilities":  [40, 44, 48, 52, 57],
    }, index=periods)
    return income, balance


def test_chart_renders_with_complete_data():
    income, balance = _sample_data()
    fig = build_ccc_chart(income, balance)
    assert isinstance(fig, go.Figure)
    # Should have DSO + DIO + DPO + CCC traces
    trace_names = [tr.name for tr in fig.data]
    for needed in ("DSO", "DIO", "DPO", "CCC"):
        assert needed in trace_names, f"missing {needed} trace"


def test_chart_renders_empty_state_gracefully():
    fig = build_ccc_chart(pd.DataFrame(), pd.DataFrame())
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 0


def test_breakdown_table_has_4_columns():
    income, balance = _sample_data()
    df = build_ccc_breakdown_table(income, balance)
    assert not df.empty
    assert set(df.columns) >= {"DSO", "DIO", "DPO", "CCC"}


def test_breakdown_empty_when_no_data():
    df = build_ccc_breakdown_table(pd.DataFrame(), pd.DataFrame())
    assert df.empty
