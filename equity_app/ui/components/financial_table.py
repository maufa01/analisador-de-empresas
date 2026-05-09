"""
Custom HTML financial-statement table.

Replaces ``st.dataframe`` for the Financials tab so we can deliver:
- pretty period headers (FY 2023 instead of "2023-09-30 00:00:00")
- pretty account labels (Cost of Revenue instead of costOfRevenue)
- compact $/B/M number formatting + tabular nums + parentheses-for-negative
- subtotal rows with a top border and medium font weight
- ASSETS / LIABILITIES / EQUITY section headers (gold uppercase)
- a YoY % column on the right (green / red)
- three view modes: ABSOLUTE · COMMON SIZE · GROWTH

CRITICAL: the entire HTML body is concatenated with NO newlines or
leading whitespace before being passed to ``st.markdown(unsafe_allow_html=True)``.
Streamlit's markdown parser runs first — any line indented ≥4 spaces
becomes a code block and the HTML leaks to the page as literal text.
That's the same trap that broke ``score_breakdown.py`` earlier.
"""
from __future__ import annotations
from typing import Iterable, Literal, Optional

import math
import pandas as pd

import streamlit as st

from core.account_labels import (
    INCOME_STATEMENT_ORDER, BALANCE_SHEET_ORDER, CASH_FLOW_ORDER,
    INCOME_STATEMENT_LAYOUT, BALANCE_SHEET_LAYOUT, CASH_FLOW_LAYOUT,
    CAGR_ELIGIBLE_ROWS, DerivedRow,
    SECTION_LABELS, get_label,
)
from core.formatters import (
    format_financial_number, format_percentage, format_period, format_yoy,
)


ViewMode = Literal["absolute", "common_size", "growth", "hybrid"]


_THEAD_STYLE = (
    "background:#1A2033;"
)
_TH_BASE_STYLE = (
    "padding:10px 14px; font-size:11px; letter-spacing:0.6px; "
    "text-transform:uppercase; color:#9CA3AF; font-weight:500;"
)
_ROW_BASE_STYLE = "color:#E8EAED; font-size:13px;"
_CELL_PAD = "padding:9px 14px;"
_RIGHT_CELL = (
    "text-align:right; font-variant-numeric:tabular-nums; "
    f"{_CELL_PAD}"
)
_LABEL_CELL = f"text-align:left; {_CELL_PAD}"


# ============================================================
# Internals
# ============================================================
def _resolve_value(
    df: pd.DataFrame, key: str, period: pd.Timestamp,
) -> Optional[float]:
    """Return df.loc[period, key] tolerating missing keys / NaNs."""
    if key not in df.columns:
        return None
    try:
        v = df.loc[period, key]
    except KeyError:
        return None
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _section_header_row(label: str, n_periods: int) -> str:
    """One <tr> for an ASSETS / LIABILITIES / EQUITY separator."""
    cell = (
        f'<td colspan="{n_periods + 2}" '
        f'style="{_LABEL_CELL} background:#1A2033; '
        f'color:#C9A961; font-size:11px; letter-spacing:0.6px; '
        f'text-transform:uppercase; font-weight:500; padding-top:14px;">'
        f'{label}</td>'
    )
    return f'<tr>{cell}</tr>'


def _compute_view_value(
    raw_value: Optional[float],
    *,
    view: ViewMode,
    base_value: Optional[float] = None,
    prior_value: Optional[float] = None,
) -> Optional[float]:
    """
    Convert the raw value into the displayed value for the chosen view.

    - absolute    → raw_value
    - common_size → raw / base   (base = revenue or total assets)
    - growth      → (raw / prior − 1) × 100
    """
    if raw_value is None:
        return None
    if view == "absolute":
        return raw_value
    if view == "common_size":
        if base_value is None or base_value == 0:
            return None
        return raw_value / base_value * 100.0
    if view == "growth":
        if prior_value is None or prior_value == 0:
            return None
        return (raw_value / prior_value - 1.0) * 100.0
    return raw_value


def _format_view_value(value: Optional[float], *, view: ViewMode) -> str:
    if value is None:
        return "—"
    if view == "absolute":
        return format_financial_number(value, parens_for_negative=True)
    # Both common_size and growth render as %
    return format_percentage(value, decimals=1, show_sign=(view == "growth"))


# ============================================================
# Public API
# ============================================================
def render_financial_table(
    df: pd.DataFrame,
    *,
    order: list[tuple[str, str]],
    view: ViewMode = "absolute",
    base_keys: tuple[str, ...] = ("revenue",),
    show_yoy: bool = True,
    table_label: str = "($USD)",
) -> None:
    """
    Args:
        df:        wide DataFrame indexed by fiscal-period-end, one row per
                   period, one column per account (camelCase keys).
        order:     list of (key, kind) where kind ∈ {row, subtotal, section}.
                   Use ``INCOME_STATEMENT_ORDER`` etc. from account_labels.
        view:      absolute · common_size · growth
        base_keys: when ``view == "common_size"``, the row whose value
                   becomes the denominator for each period. The first
                   key found in ``df`` is used.
        show_yoy:  appends a "YoY" column (only meaningful in absolute view).
    """
    if df is None or df.empty:
        st.info("No data available for this statement.")
        return

    df = df.sort_index()
    periods: list[pd.Timestamp] = list(df.index)
    n = len(periods)

    # Resolve the common-size base (first available denominator key)
    base_key: Optional[str] = None
    if view == "common_size":
        for k in base_keys:
            if k in df.columns:
                base_key = k
                break

    # ---- Build header ----
    header_cells: list[str] = []
    header_cells.append(
        f'<th style="{_TH_BASE_STYLE} text-align:left;">{table_label}</th>'
    )
    for p in periods:
        header_cells.append(
            f'<th style="{_TH_BASE_STYLE} text-align:right;">{format_period(p)}</th>'
        )
    if show_yoy and view == "absolute" and n >= 2:
        header_cells.append(
            f'<th style="{_TH_BASE_STYLE} text-align:right; color:#C9A961;">YoY</th>'
        )

    head_html = (
        f'<thead><tr style="{_THEAD_STYLE}">'
        + "".join(header_cells)
        + '</tr></thead>'
    )

    # ---- Build body rows ----
    body_rows: list[str] = []
    for key, kind in order:
        if kind == "section":
            label = SECTION_LABELS.get(key, key)
            extra = (1 if (show_yoy and view == "absolute" and n >= 2) else 0)
            body_rows.append(_section_header_row(label, n + extra - 1))
            continue

        # Skip rows whose data isn't in this fixture
        if key not in df.columns:
            continue

        is_subtotal = (kind == "subtotal")

        cells: list[str] = []
        # Label cell
        label_color = "#E8EAED"
        label_weight = "500" if is_subtotal else "400"
        cells.append(
            f'<td style="{_LABEL_CELL} color:{label_color}; '
            f'font-weight:{label_weight};">{get_label(key)}</td>'
        )

        # Per-period value cells
        for i, period in enumerate(periods):
            raw = _resolve_value(df, key, period)
            base_value = (_resolve_value(df, base_key, period)
                          if base_key else None)
            prior_raw = (_resolve_value(df, key, periods[i - 1])
                         if (view == "growth" and i >= 1) else None)
            disp = _compute_view_value(
                raw, view=view, base_value=base_value, prior_value=prior_raw,
            )
            text = _format_view_value(disp, view=view)
            color = "#E8EAED" if disp is not None and disp >= 0 else "#9CA3AF"
            if view == "growth" and disp is not None:
                color = "#10B981" if disp >= 0 else "#EF4444"
            cells.append(
                f'<td style="{_RIGHT_CELL} color:{color}; '
                f'font-weight:{label_weight};">{text}</td>'
            )

        # YoY column (only in absolute view)
        if show_yoy and view == "absolute" and n >= 2:
            last_raw = _resolve_value(df, key, periods[-1])
            prev_raw = _resolve_value(df, key, periods[-2])
            yoy_text, yoy_color = format_yoy(last_raw, prev_raw, decimals=2)
            cells.append(
                f'<td style="{_RIGHT_CELL} color:{yoy_color};">{yoy_text}</td>'
            )

        # Border-top on subtotals
        row_style = _ROW_BASE_STYLE
        if is_subtotal:
            row_style += " border-top:1px solid #1F2937;"
        # Zebra stripe on regular rows for legibility
        elif len(body_rows) % 2 == 1:
            row_style += " background:rgba(255,255,255,0.02);"

        body_rows.append(f'<tr style="{row_style}">' + "".join(cells) + "</tr>")

    body_html = "<tbody>" + "".join(body_rows) + "</tbody>"

    table_html = (
        '<div style="background:#131826; border:1px solid #1F2937; '
        'border-radius:8px; overflow:auto;">'
        '<table style="width:100%; border-collapse:collapse; '
        'font-variant-numeric:tabular-nums; '
        'font-family:Inter,-apple-system,sans-serif;">'
        + head_html + body_html
        + '</table></div>'
    )
    st.markdown(table_html, unsafe_allow_html=True)


# ============================================================
# HYBRID VIEW — analyst-spreadsheet style
# (absolute rows + derived % rows interleaved + TTM + N-year CAGR)
# ============================================================
from analysis.ratios import cagr as _cagr
from analysis.ttm import (
    compute_ttm_income, compute_ttm_balance, compute_ttm_cash,
)


def _compute_derived_value(
    spec: DerivedRow,
    df: pd.DataFrame,
    period: pd.Timestamp,
    prev_period: Optional[pd.Timestamp],
) -> Optional[float]:
    """Resolve the value of a DerivedRow at a given period."""
    base = _resolve_value(df, spec.base_row, period)
    if base is None:
        return None

    if spec.style == "yoy":
        if prev_period is None:
            return None
        prev = _resolve_value(df, spec.base_row, prev_period)
        if prev is None or prev == 0:
            return None
        return base / prev - 1.0

    if spec.style == "margin_of_revenue":
        rev = _resolve_value(df, "revenue", period)
        if rev is None or rev == 0:
            return None
        return base / rev

    if spec.style == "of_total_assets":
        tot = _resolve_value(df, "totalAssets", period)
        if tot is None or tot == 0:
            return None
        return base / tot

    if spec.style == "of_total_liabilities":
        tot = _resolve_value(df, "totalLiabilities", period)
        if tot is None or tot == 0:
            return None
        return base / tot

    if spec.style == "tax_rate":
        if not spec.ref_row:
            return None
        ref = _resolve_value(df, spec.ref_row, period)
        if ref is None or ref == 0:
            return None
        return base / ref

    if spec.style == "capex_margin":
        rev = _resolve_value(df, "revenue", period)
        if rev is None or rev == 0:
            return None
        return base / rev          # capex itself is negative — margin is too

    return None


def _format_pct_cell(value: Optional[float], color_by_sign: bool) -> str:
    if value is None:
        return f'<td style="{_RIGHT_CELL} color:#4B5563;">—</td>'
    pct = value * 100.0
    if color_by_sign:
        color = "#10B981" if pct > 0 else ("#B87333" if pct < 0 else "#9CA3AF")
        sign = "+" if pct > 0 else ""
    else:
        color = "#9CA3AF"
        sign = ""
    return (
        f'<td style="{_RIGHT_CELL} color:{color}; font-size:12px;">'
        f'{sign}{pct:.2f}%</td>'
    )


def _cagr_for(df: pd.DataFrame, key: str, periods: int) -> Optional[float]:
    if key not in df.columns:
        return None
    s = df[key].dropna()
    if len(s) < periods + 1:
        return None
    val = _cagr(s, periods=periods)
    return None if (val is None or math.isnan(val)) else float(val)


def _ttm_value(ttm: Optional[pd.Series], key: str) -> Optional[float]:
    if ttm is None or key not in ttm.index:
        return None
    v = ttm[key]
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _ttm_derived_value(
    spec: DerivedRow, ttm: Optional[pd.Series],
) -> Optional[float]:
    """Compute a derived row's TTM value when meaningful (margins, tax rate).
    YoY and other "of-period" styles don't have a TTM analogue."""
    if ttm is None:
        return None
    base = _ttm_value(ttm, spec.base_row)
    if base is None:
        return None
    if spec.style == "margin_of_revenue":
        rev = _ttm_value(ttm, "revenue")
        return (base / rev) if (rev and rev != 0) else None
    if spec.style == "tax_rate" and spec.ref_row:
        ref = _ttm_value(ttm, spec.ref_row)
        return (base / ref) if (ref and ref != 0) else None
    if spec.style == "capex_margin":
        rev = _ttm_value(ttm, "revenue")
        return (base / rev) if (rev and rev != 0) else None
    return None


def _render_hybrid(
    df: pd.DataFrame,
    *,
    layout: list,
    table_label: str,
    ttm: Optional[pd.Series],
    show_ttm: bool,
    show_cagr: bool,
) -> None:
    df = df.sort_index()
    periods: list[pd.Timestamp] = list(df.index)

    # --- header ---
    header_cells: list[str] = [
        f'<th style="{_TH_BASE_STYLE} text-align:left;">{table_label}</th>'
    ]
    for p in periods:
        header_cells.append(
            f'<th style="{_TH_BASE_STYLE} text-align:right;">{format_period(p)}</th>'
        )
    if show_ttm:
        header_cells.append(
            f'<th style="{_TH_BASE_STYLE} text-align:right; color:#C9A961;">TTM</th>'
        )
    if show_cagr:
        header_cells.append(
            f'<th style="{_TH_BASE_STYLE} text-align:right;">5Y CAGR</th>'
        )
        header_cells.append(
            f'<th style="{_TH_BASE_STYLE} text-align:right;">10Y CAGR</th>'
        )
    head_html = (
        f'<thead><tr style="{_THEAD_STYLE}">' + "".join(header_cells) + '</tr></thead>'
    )

    n_extra_cols = (1 if show_ttm else 0) + (2 if show_cagr else 0)
    body_rows: list[str] = []

    for entry in layout:
        spec, role = entry

        # Section header (ASSETS / LIABILITIES / EQUITY)
        if role == "section_header":
            label = SECTION_LABELS.get(spec, str(spec).strip("_").upper())
            body_rows.append(_section_header_row(label, len(periods) + n_extra_cols - 1))
            continue

        # Derived row (interleaved % rows)
        if isinstance(spec, DerivedRow):
            cells: list[str] = []
            indent_px = 24 * spec.indent
            cells.append(
                f'<td style="padding:4px 14px 4px {indent_px}px; '
                f'color:#6B7280; font-size:11px; font-style:italic;">{spec.label}</td>'
            )
            prev_period: Optional[pd.Timestamp] = None
            for period in periods:
                v = _compute_derived_value(spec, df, period, prev_period)
                cells.append(_format_pct_cell(v, spec.color_by_sign))
                prev_period = period
            if show_ttm:
                cells.append(_format_pct_cell(_ttm_derived_value(spec, ttm),
                                              spec.color_by_sign))
            if show_cagr:
                if (spec.style == "yoy"
                        and spec.base_row in CAGR_ELIGIBLE_ROWS):
                    for p in (5, 10):
                        cells.append(_format_pct_cell(
                            _cagr_for(df, spec.base_row, p),
                            color_by_sign=True,
                        ))
                else:
                    cells.append(f'<td style="{_RIGHT_CELL} color:#4B5563;">—</td>')
                    cells.append(f'<td style="{_RIGHT_CELL} color:#4B5563;">—</td>')
            body_rows.append(
                f'<tr style="background:rgba(255,255,255,0.015);">'
                + "".join(cells) + "</tr>"
            )
            continue

        # Absolute row
        key = spec
        if key not in df.columns:
            continue
        is_subtotal = (role == "subtotal")
        weight = "500" if is_subtotal else "400"
        border = "border-top:1px solid #1F2937;" if is_subtotal else ""

        cells = [
            f'<td style="{_LABEL_CELL} color:#E8EAED; '
            f'font-weight:{weight}; {border}">{get_label(key)}</td>'
        ]
        for period in periods:
            v = _resolve_value(df, key, period)
            text = format_financial_number(v, parens_for_negative=True) if v is not None else "—"
            cells.append(
                f'<td style="{_RIGHT_CELL} color:#E8EAED; '
                f'font-weight:{weight}; {border}">{text}</td>'
            )

        if show_ttm:
            v = _ttm_value(ttm, key)
            if v is None:
                cells.append(
                    f'<td style="{_RIGHT_CELL} color:#4B5563; {border}">—</td>'
                )
            else:
                cells.append(
                    f'<td style="{_RIGHT_CELL} color:#C9A961; '
                    f'font-weight:{weight}; {border}">'
                    f'{format_financial_number(v, parens_for_negative=True)}</td>'
                )

        if show_cagr:
            if key in CAGR_ELIGIBLE_ROWS:
                for p in (5, 10):
                    cells.append(_format_pct_cell(
                        _cagr_for(df, key, p), color_by_sign=True,
                    ))
            else:
                cells.append(f'<td style="{_RIGHT_CELL} color:#4B5563; {border}">—</td>')
                cells.append(f'<td style="{_RIGHT_CELL} color:#4B5563; {border}">—</td>')

        body_rows.append(f'<tr style="{_ROW_BASE_STYLE}">' + "".join(cells) + "</tr>")

    body_html = "<tbody>" + "".join(body_rows) + "</tbody>"
    table_html = (
        '<div style="background:#131826; border:1px solid #1F2937; '
        'border-radius:8px; overflow:auto;">'
        '<table style="width:100%; border-collapse:collapse; '
        'font-variant-numeric:tabular-nums; '
        'font-family:Inter,-apple-system,sans-serif;">'
        + head_html + body_html + '</table></div>'
    )
    st.markdown(table_html, unsafe_allow_html=True)


# ============================================================
# Convenience wrappers
# ============================================================
def render_income_statement(
    df: pd.DataFrame,
    *,
    view: ViewMode = "absolute",
    quarterly: Optional[pd.DataFrame] = None,
    show_ttm: bool = True,
    show_cagr: bool = True,
) -> None:
    if df is None or df.empty:
        st.info("No income statement data available.")
        return
    if view == "hybrid":
        ttm = compute_ttm_income(quarterly) if (show_ttm and quarterly is not None) else None
        _render_hybrid(
            df, layout=INCOME_STATEMENT_LAYOUT,
            table_label="INCOME STATEMENT ($USD)",
            ttm=ttm, show_ttm=show_ttm, show_cagr=show_cagr,
        )
        return
    render_financial_table(
        df, order=INCOME_STATEMENT_ORDER, view=view,
        base_keys=("revenue",),
    )


def render_balance_sheet(
    df: pd.DataFrame,
    *,
    view: ViewMode = "absolute",
    quarterly: Optional[pd.DataFrame] = None,
    show_ttm: bool = True,
    show_cagr: bool = True,
) -> None:
    if df is None or df.empty:
        st.info("No balance sheet data available.")
        return
    if view == "hybrid":
        ttm = compute_ttm_balance(quarterly) if (show_ttm and quarterly is not None) else None
        _render_hybrid(
            df, layout=BALANCE_SHEET_LAYOUT,
            table_label="BALANCE SHEET ($USD)",
            ttm=ttm, show_ttm=show_ttm, show_cagr=show_cagr,
        )
        return
    render_financial_table(
        df, order=BALANCE_SHEET_ORDER, view=view,
        base_keys=("totalAssets",),
    )


def render_cash_flow(
    df: pd.DataFrame,
    *,
    view: ViewMode = "absolute",
    quarterly: Optional[pd.DataFrame] = None,
    show_ttm: bool = True,
    show_cagr: bool = True,
) -> None:
    if df is None or df.empty:
        st.info("No cash flow data available.")
        return
    if view == "hybrid":
        ttm = compute_ttm_cash(quarterly) if (show_ttm and quarterly is not None) else None
        _render_hybrid(
            df, layout=CASH_FLOW_LAYOUT,
            table_label="CASH FLOW ($USD)",
            ttm=ttm, show_ttm=show_ttm, show_cagr=show_cagr,
        )
        return
    render_financial_table(
        df, order=CASH_FLOW_ORDER, view=view,
        base_keys=("revenue",),                  # CF / revenue is conventional
    )
