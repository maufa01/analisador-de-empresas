"""
Next-earnings card for the Overview tab.

Renders nothing when no earnings is scheduled in the next 60 days —
the card is "out of sight, out of mind" until the date matters.

Driven by Finnhub's calendar/earnings endpoint. Empty when the key
isn't configured; the page still works.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import streamlit as st


def render_next_earnings_card(ticker: str, *, horizon_days: int = 60) -> None:
    try:
        from data.finnhub_provider import fetch_earnings_calendar, is_available
    except Exception:
        return
    if not is_available():
        return

    today = datetime.utcnow().date()
    horizon = today + timedelta(days=horizon_days)
    try:
        df = fetch_earnings_calendar(
            ticker, from_date=today.isoformat(), to_date=horizon.isoformat(),
        )
    except Exception:
        return
    if df is None or df.empty or "date" not in df.columns:
        return

    upcoming = df[df["date"] >= pd.Timestamp(today)]
    if upcoming.empty:
        return

    row = upcoming.iloc[0]
    earn_date = pd.Timestamp(row["date"])
    days_to = (earn_date.date() - today).days

    if days_to <= 7:
        urgency = "THIS WEEK"
        color = "var(--accent)"
    elif days_to <= 14:
        urgency = "Next 2 weeks"
        color = "var(--accent)"
    else:
        urgency = f"In {days_to} days"
        color = "var(--text-muted)"

    eps_est = row.get("epsEstimate")
    rev_est = row.get("revenueEstimate")
    hour = (row.get("hour") or "").lower()
    hour_str = ("Before market open" if hour == "bmo"
                else "After market close" if hour == "amc"
                else "")

    eps_str = f"${eps_est:.2f}" if isinstance(eps_est, (int, float)) and pd.notna(eps_est) else "—"
    rev_str = ""
    if isinstance(rev_est, (int, float)) and pd.notna(rev_est) and rev_est > 0:
        if rev_est >= 1e9:
            rev_str = f"${rev_est/1e9:,.2f}B"
        elif rev_est >= 1e6:
            rev_str = f"${rev_est/1e6:,.0f}M"
        else:
            rev_str = f"${rev_est:,.0f}"

    st.markdown(
        '<div class="eq-card" style="padding:14px 18px; '
        f'border-left:3px solid {color}; margin:14px 0;">'
        '<div style="display:flex; justify-content:space-between; '
        'align-items:baseline; gap:18px; flex-wrap:wrap;">'
        '<div>'
        '<div class="eq-idx-label">NEXT EARNINGS</div>'
        f'<div style="color:var(--text-primary); font-size:18px; '
        f'font-weight:500; margin-top:4px;">'
        f'{earn_date.strftime("%b %d, %Y")}</div>'
        f'<div style="color:{color}; font-size:12px; margin-top:2px;">'
        f'{urgency}{(" · " + hour_str) if hour_str else ""}</div>'
        '</div>'
        '<div style="text-align:right;">'
        '<div class="eq-idx-label">EPS / REV ESTIMATE</div>'
        f'<div style="color:var(--text-primary); font-size:16px; '
        f'font-weight:500; font-variant-numeric:tabular-nums; margin-top:4px;">'
        f'{eps_str}{(" · " + rev_str) if rev_str else ""}</div>'
        '</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )
