"""
Combined news + sentiment section for the Overview tab.

Three cards arranged side-by-side:
    - News sentiment      → Marketaux (per-article, per-ticker score)
    - Insider sentiment   → Finnhub stock_insider_sentiment (monthly MSPR)
    - Analyst sentiment   → Finnhub stock_recommendation (12m strong-buy → strong-sell)

Below the cards: a compact list of the 10 most-recent headlines with
per-item sentiment chip.

When a key isn't configured, the corresponding card renders an empty
state ("Configure MARKETAUX_API_KEY") instead of disappearing — this
makes it obvious why the section is partial.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import streamlit as st


_DOWNSIDE = "rgba(184,115,51,1)"


def _empty_card(title: str, msg: str) -> None:
    st.markdown(
        '<div class="eq-card" style="padding:16px; '
        'color:var(--text-muted); font-size:12px; min-height:130px;">'
        f'<div class="eq-idx-label">{title}</div>'
        f'<div style="margin-top:8px; line-height:1.4;">{msg}</div></div>',
        unsafe_allow_html=True,
    )


# ============================================================
# Card 1: News sentiment (Marketaux)
# ============================================================
def _render_news_card(ticker: str, news_df: pd.DataFrame) -> None:
    if news_df is None or news_df.empty:
        _empty_card("NEWS SENTIMENT",
                    "No Marketaux news for this ticker (or "
                    "MARKETAUX_API_KEY not set).")
        return

    scores = news_df["sentiment_score"].dropna() if "sentiment_score" in news_df.columns else pd.Series(dtype=float)
    if scores.empty:
        avg, label, color = None, "No sentiment", "var(--text-muted)"
    else:
        avg = float(scores.mean())
        if avg > 0.10:
            label, color = "Positive", "var(--gains)"
        elif avg < -0.10:
            label, color = "Negative", _DOWNSIDE
        else:
            label, color = "Neutral", "var(--accent)"

    pos = int((scores > 0.10).sum())
    neg = int((scores < -0.10).sum())
    neu = int(len(scores) - pos - neg)

    avg_str = f"{avg:+.2f}" if avg is not None else "—"
    st.markdown(
        '<div class="eq-card" style="padding:16px; '
        f'border-left:3px solid {color}; min-height:130px;">'
        '<div class="eq-idx-label">NEWS SENTIMENT</div>'
        f'<div style="color:{color}; font-size:22px; font-weight:500; '
        f'letter-spacing:-0.4px; margin-top:6px;">{label}</div>'
        f'<div style="color:var(--text-primary); font-size:13px; '
        f'font-variant-numeric:tabular-nums; margin-top:4px;">'
        f'{len(news_df)} articles · avg {avg_str}</div>'
        f'<div style="color:var(--text-muted); font-size:11px; margin-top:6px;">'
        f'<span style="color:var(--gains);">{pos}+</span> · {neu}n · '
        f'<span style="color:{_DOWNSIDE};">{neg}-</span></div>'
        '</div>',
        unsafe_allow_html=True,
    )


# ============================================================
# Card 2: Insider sentiment (Finnhub)
# ============================================================
def _render_insider_card(insider: Optional[dict]) -> None:
    if not insider or not insider.get("data"):
        _empty_card("INSIDER SENTIMENT",
                    "Configure FINNHUB_API_KEY to enable insider "
                    "sentiment (monthly MSPR).")
        return

    data = insider.get("data", [])
    if not data:
        _empty_card("INSIDER SENTIMENT",
                    "No Finnhub insider sentiment for this ticker.")
        return

    latest = data[-1]
    mspr = latest.get("mspr")
    change = latest.get("change")
    if mspr is None:
        _empty_card("INSIDER SENTIMENT", "MSPR unavailable for this ticker.")
        return

    if mspr > 0:
        label, color = "Buying", "var(--gains)"
    elif mspr < 0:
        label, color = "Selling", _DOWNSIDE
    else:
        label, color = "Neutral", "var(--accent)"

    period = f"{latest.get('year', '')}-{latest.get('month', '')}".strip("-")
    chg_str = f"{change:+,.0f}" if isinstance(change, (int, float)) else "—"

    st.markdown(
        '<div class="eq-card" style="padding:16px; '
        f'border-left:3px solid {color}; min-height:130px;">'
        '<div class="eq-idx-label">INSIDER SENTIMENT · FINNHUB</div>'
        f'<div style="color:{color}; font-size:22px; font-weight:500; '
        f'letter-spacing:-0.4px; margin-top:6px;">{label}</div>'
        f'<div style="color:var(--text-primary); font-size:13px; '
        f'font-variant-numeric:tabular-nums; margin-top:4px;">'
        f'MSPR {mspr:+.3f}</div>'
        f'<div style="color:var(--text-muted); font-size:11px; margin-top:6px;">'
        f'Period {period} · net Δshares {chg_str}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


# ============================================================
# Card 3: Analyst recommendations (Finnhub)
# ============================================================
def _render_analyst_card(recs_df: Optional[pd.DataFrame]) -> None:
    if recs_df is None or recs_df.empty:
        _empty_card("ANALYST SENTIMENT",
                    "Configure FINNHUB_API_KEY to enable analyst "
                    "recommendation trends.")
        return

    latest = recs_df.iloc[0]
    sb = int(latest.get("strongBuy", 0) or 0)
    b  = int(latest.get("buy", 0) or 0)
    h  = int(latest.get("hold", 0) or 0)
    s  = int(latest.get("sell", 0) or 0)
    ss = int(latest.get("strongSell", 0) or 0)
    total = sb + b + h + s + ss
    if total == 0:
        _empty_card("ANALYST SENTIMENT", "No analyst data for this ticker.")
        return

    bullish = sb + b
    bearish = s + ss
    if bullish > 2 * bearish:
        label, color = "Bullish", "var(--gains)"
    elif bearish > 2 * bullish:
        label, color = "Bearish", _DOWNSIDE
    else:
        label, color = "Mixed", "var(--accent)"

    period_str = ""
    if "period" in latest and pd.notna(latest["period"]):
        period_str = pd.Timestamp(latest["period"]).strftime("%b %Y")

    st.markdown(
        '<div class="eq-card" style="padding:16px; '
        f'border-left:3px solid {color}; min-height:130px;">'
        '<div class="eq-idx-label">ANALYST SENTIMENT · FINNHUB</div>'
        f'<div style="color:{color}; font-size:22px; font-weight:500; '
        f'letter-spacing:-0.4px; margin-top:6px;">{label}</div>'
        f'<div style="color:var(--text-primary); font-size:13px; '
        f'font-variant-numeric:tabular-nums; margin-top:4px;">'
        f'{bullish} buys / {h} holds / {bearish} sells</div>'
        f'<div style="color:var(--text-muted); font-size:11px; margin-top:6px;">'
        f'{total} analysts · {period_str}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


# ============================================================
# Headlines list — uses Marketaux items (sentiment per-article)
# ============================================================
def _render_news_list(news_df: pd.DataFrame, *, limit: int = 10) -> None:
    if news_df is None or news_df.empty:
        return
    st.markdown(
        '<div class="eq-section-label" style="margin-top:14px;">'
        'RECENT HEADLINES</div>',
        unsafe_allow_html=True,
    )
    items_html = ""
    for _, row in news_df.head(limit).iterrows():
        sv = float(row.get("sentiment_score") or 0.0) if pd.notna(row.get("sentiment_score")) else 0.0
        chip = ("var(--gains)" if sv > 0.10
                else _DOWNSIDE if sv < -0.10
                else "var(--text-muted)")
        title = str(row.get("title", "") or "").replace("<", "&lt;").replace(">", "&gt;")
        source = str(row.get("source", "") or "")
        link = str(row.get("url", "") or "#")
        ts = row.get("published")
        ts_str = pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M") if pd.notna(ts) else "—"

        items_html += (
            '<div style="padding:12px 0; border-bottom:1px solid var(--border); '
            'display:flex; gap:14px; justify-content:space-between;">'
            '<div style="flex:1; min-width:0;">'
            f'<a href="{link}" target="_blank" '
            'style="color:var(--text-primary); text-decoration:none; font-size:14px;">'
            f'{title}</a>'
            f'<div style="color:var(--text-muted); font-size:11px; margin-top:4px;">'
            f'{source} · {ts_str}</div>'
            '</div>'
            f'<div style="color:{chip}; font-size:12px; '
            f'font-variant-numeric:tabular-nums; white-space:nowrap;">'
            f'{sv:+.2f}</div>'
            '</div>'
        )
    st.markdown(
        '<div class="eq-card" style="padding:6px 18px; margin-top:6px;">'
        + items_html + '</div>',
        unsafe_allow_html=True,
    )


# ============================================================
# Public entry point
# ============================================================
def render_news_combined_section(ticker: str) -> None:
    """Pull from both providers + render the 3-card row + headlines list."""
    st.markdown(
        '<div class="eq-section-label">NEWS &amp; SENTIMENT</div>',
        unsafe_allow_html=True,
    )

    # Marketaux news — gracefully empty when no key
    news_df: pd.DataFrame
    try:
        from data.marketaux_provider import fetch_news as _fetch_marketaux, is_available as _mx_avail
        news_df = _fetch_marketaux(ticker, limit=20) if _mx_avail() else pd.DataFrame()
    except Exception:
        news_df = pd.DataFrame()

    # Finnhub insider sentiment + recs — gracefully empty when no key
    try:
        from data.finnhub_provider import (
            is_available as _fh_avail,
            fetch_recommendation_trends,
        )
    except Exception:
        _fh_avail = lambda: False  # noqa: E731
        fetch_recommendation_trends = lambda *a, **k: pd.DataFrame()  # noqa: E731

    insider_data: Optional[dict] = None
    recs_df: Optional[pd.DataFrame] = None
    if _fh_avail():
        # Finnhub's insider-sentiment endpoint is GET /stock/insider-sentiment
        # Not yet exposed in finnhub_provider, so call it through the same
        # _get helper using a local import to keep this component self-contained.
        try:
            from data.finnhub_provider import _get as _fh_get
            from datetime import datetime, timedelta
            today = datetime.utcnow().date()
            from_d = (today - timedelta(days=365)).isoformat()
            insider_data = _fh_get("stock/insider-sentiment", {
                "symbol": ticker,
                "from":   from_d,
                "to":     today.isoformat(),
            })
        except Exception:
            insider_data = None
        try:
            recs_df = fetch_recommendation_trends(ticker)
        except Exception:
            recs_df = None

    # Three-card row
    c1, c2, c3 = st.columns(3, gap="small")
    with c1: _render_news_card(ticker, news_df)
    with c2: _render_insider_card(insider_data)
    with c3: _render_analyst_card(recs_df)

    # Headlines list (Marketaux only — it's the source with per-article sentiment)
    _render_news_list(news_df, limit=10)
