"""
Data source badge — small inline indicator showing where a value came
from + how fresh it is.

Usage:
    render_value_with_source(
        label="Current price", value="$245.32",
        source="finnhub", fetched_at=quote["fetched_at"],
        is_realtime=True,
    )

Conventions:
    finnhub   — green (real-time)
    fred      — green (official Fed)
    sec       — gold (official SEC EDGAR)
    yfinance  — grey (15-min delayed)
    marketaux — grey (news)
    fmp       — gold (premium aggregator)
    cache     — dim grey (stale-but-acceptable)
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional

import streamlit as st


_SOURCE_COLORS = {
    "finnhub":    "var(--gains)",
    "fred":       "var(--gains)",
    "sec":        "var(--accent)",
    "fmp":        "var(--accent)",
    "yfinance":   "var(--text-secondary)",
    "marketaux":  "var(--text-secondary)",
    "cache":      "var(--text-muted)",
    "fixture":    "rgba(184,115,51,1)",   # red flag — should never appear
}


def _age_text(fetched_at: Optional[datetime]) -> str:
    if fetched_at is None:
        return ""
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - fetched_at
    if age < timedelta(minutes=1):
        return "now"
    if age < timedelta(hours=1):
        return f"{age.seconds // 60}m ago"
    if age < timedelta(days=1):
        return f"{age.seconds // 3600}h ago"
    return f"{age.days}d ago"


def render_value_with_source(
    label: str,
    value: str,
    source: str,
    *,
    fetched_at: Optional[datetime] = None,
    is_realtime: bool = False,
) -> None:
    """Inline value display with provider + age."""
    color = _SOURCE_COLORS.get(source.lower(), "var(--text-muted)")
    realtime = " · LIVE" if is_realtime else ""
    age = _age_text(fetched_at)
    st.markdown(
        '<div style="margin:8px 0;">'
        '<div style="color:var(--text-muted); font-size:10px; '
        'text-transform:uppercase; letter-spacing:0.6px; margin-bottom:2px;">'
        f'{label}</div>'
        '<div style="color:var(--text-primary); font-size:24px; '
        f'font-weight:500; font-variant-numeric:tabular-nums;">{value}</div>'
        '<div style="display:flex; gap:8px; margin-top:4px; font-size:10px;">'
        f'<span style="color:{color}; text-transform:uppercase; '
        f'letter-spacing:0.4px;">● {source}{realtime}</span>'
        + (f'<span style="color:var(--text-muted);">{age}</span>'
           if age else "")
        + '</div></div>',
        unsafe_allow_html=True,
    )


def source_chip(source: str, *, fetched_at: Optional[datetime] = None,
                is_realtime: bool = False) -> str:
    """Returns inline-HTML chip for a source — for inline placement next
    to an existing metric / header that already shows the value itself."""
    color = _SOURCE_COLORS.get(source.lower(), "var(--text-muted)")
    realtime = " LIVE" if is_realtime else ""
    age = _age_text(fetched_at)
    age_html = (f' <span style="color:var(--text-muted);">· {age}</span>'
                if age else "")
    return (
        f'<span style="color:{color}; font-size:10px; '
        f'text-transform:uppercase; letter-spacing:0.4px; '
        f'font-variant-numeric:tabular-nums;">'
        f'● {source}{realtime}</span>{age_html}'
    )
