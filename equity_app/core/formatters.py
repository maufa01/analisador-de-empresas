"""
Display formatters for financial values, ratios, percentages, and periods.

Pure functions — no Streamlit, no pandas (other than NaN check). Used by
``ui/components/financial_table`` and any other component that needs the
same compact $/%/period rendering.
"""
from __future__ import annotations
from typing import Optional, Union

import math


Numeric = Union[int, float, None]


def _is_missing(v: Numeric) -> bool:
    if v is None:
        return True
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return True


# ============================================================
# Money — compact T/B/M/K notation
# ============================================================
def format_financial_number(
    value: Numeric,
    *,
    decimals: int = 2,
    parens_for_negative: bool = False,
) -> str:
    """
    ``$365.82B`` style. Negatives as ``-`` by default; pass
    ``parens_for_negative=True`` for ``($1.23B)`` accounting style.
    """
    if _is_missing(value):
        return "—"
    v = float(value)
    av = abs(v)
    if   av >= 1e12: body = f"${av / 1e12:.{decimals}f}T"
    elif av >= 1e9:  body = f"${av / 1e9:.{decimals}f}B"
    elif av >= 1e6:  body = f"${av / 1e6:.{decimals}f}M"
    elif av >= 1e3:  body = f"${av / 1e3:.{decimals}f}K"
    else:            body = f"${av:.{decimals}f}"

    if v < 0:
        return f"({body})" if parens_for_negative else f"-{body}"
    return body


# ============================================================
# Percentages
# ============================================================
def format_percentage(
    value: Numeric,
    *,
    decimals: int = 2,
    show_sign: bool = False,
) -> str:
    """Pass values that are already in % units (e.g. 25.31, not 0.2531)."""
    if _is_missing(value):
        return "—"
    v = float(value)
    sign = ("+" if v > 0 else "") if show_sign else ""
    return f"{sign}{v:.{decimals}f}%"


def format_ratio(value: Numeric, *, decimals: int = 2) -> str:
    """Plain decimal — e.g. Debt/Equity ``1.87``."""
    if _is_missing(value):
        return "—"
    return f"{float(value):.{decimals}f}"


def format_multiple(value: Numeric, *, decimals: int = 1) -> str:
    """Multiple with ``x`` suffix — e.g. ``28.5x``."""
    if _is_missing(value):
        return "—"
    return f"{float(value):.{decimals}f}x"


# ============================================================
# Periods (column headers)
# ============================================================
def format_period(date) -> str:
    """
    ``"FY 2023"`` style. Honors fiscal-year shifts: month >= 7 ⇒ FY = year,
    month < 7 ⇒ FY = year − 1 (so Apple's Sep-2023 close stays "FY 2023"
    while Microsoft's Jun-2023 close stays "FY 2023" but a Mar-2023 close
    rolls back to "FY 2022").
    """
    import pandas as pd
    if date is None:
        return "—"
    try:
        dt = pd.to_datetime(date)
    except Exception:
        return str(date)
    fy = dt.year if dt.month >= 7 else dt.year - 1
    return f"FY {fy}"


# ============================================================
# YoY change — returns (formatted_string, color_var)
# ============================================================
def format_yoy(current: Numeric, prior: Numeric, *, decimals: int = 2) -> tuple[str, str]:
    """
    Returns ``(text, css_color_var)`` so the table renderer can colour
    the cell. Uses the project palette CSS vars.
    """
    if _is_missing(current) or _is_missing(prior):
        return "—", "var(--text-muted)"
    p = float(prior)
    if p == 0:
        return "—", "var(--text-muted)"
    pct = (float(current) / p - 1.0) * 100.0
    sign = "+" if pct >= 0 else ""
    txt = f"{sign}{pct:.{decimals}f}%"
    color = "var(--gains)" if pct >= 0 else "var(--losses)"
    return txt, color


__all__ = [
    "format_financial_number",
    "format_percentage",
    "format_ratio",
    "format_multiple",
    "format_period",
    "format_yoy",
    "safe_fmt",
]


def safe_fmt(value, fmt: str = ".2f", default: str = "—") -> str:
    """Robust ``format()`` wrapper: ``None`` / ``NaN`` / ``inf`` / non-numeric
    inputs return ``default`` instead of raising ``TypeError``.

    Use anywhere a Python f-string format-spec might receive missing data
    (e.g. ``{result.avg_5y_ccc:.0f}`` exploding when the ratio is None
    for a utility / software company without inventory tracking).
    """
    import math
    if value is None:
        return default
    try:
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return default
        return format(value, fmt)
    except (ValueError, TypeError):
        return default
