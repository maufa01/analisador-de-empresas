"""Generic single-ticker price history chart — reuses S&P palette."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from ui.charts.sp500_chart import build_sp500_figure


def build_price_history_figure(
    history: pd.DataFrame,
    *,
    height: int = 280,
) -> go.Figure:
    """Same look as the S&P chart — direction-colored line + soft fill."""
    return build_sp500_figure(history, height=height)
