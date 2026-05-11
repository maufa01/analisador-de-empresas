"""
Compare — Reverse DCF side-by-side cards.

For each ticker, runs the reverse-DCF solver against its current price
under a per-ticker WACC, then renders a card with implied stage-1
growth vs the trailing 5y revenue CAGR. A coloured gap badge flags
whether the market is pricing in materially more / less than realised
growth.

Cards are rendered with `st.columns` so 2-3 tickers fit comfortably
side-by-side at typical desktop widths.
"""
from __future__ import annotations
from typing import Optional

import numpy as np
import streamlit as st


def _gap_color(gap_pp: float) -> str:
    """Color buckets for |gap_pp|: <1pp green, 1-3pp amber, >3pp copper."""
    a = abs(gap_pp)
    if a < 1.0:
        return "#10B981"   # green — fair
    if a < 3.0:
        return "#C9A961"   # gold — modest mispricing
    return "#B87333"        # copper — material gap


def _card_html(*, ticker: str, implied: Optional[float],
                historical: Optional[float], gap_color: str,
                gap_text: str, interpretation: str,
                error: Optional[str] = None) -> str:
    if error:
        return (
            f'<div style="background:#181D2C; border:1px solid #1F2937; '
            f'border-radius:8px; padding:14px;">'
            f'<div style="color:#9CA3AF; font-size:11px; '
            f'letter-spacing:0.6px; text-transform:uppercase;">'
            f'{ticker}</div>'
            f'<div style="color:#6B7280; font-size:13px; margin-top:18px;">'
            f'{error}</div>'
            f'</div>'
        )

    implied_str = (f"{implied*100:+.1f}%" if implied is not None
                   else "—")
    hist_str = (f"{historical*100:+.1f}%" if historical is not None
                else "—")
    return (
        f'<div style="background:#181D2C; border:1px solid #1F2937; '
        f'border-radius:8px; padding:14px;">'
        f'<div style="color:#9CA3AF; font-size:11px; letter-spacing:0.6px; '
        f'text-transform:uppercase;">{ticker} · IMPLIED GROWTH</div>'
        f'<div style="color:#E5E7EB; font-size:30px; font-weight:600; '
        f'letter-spacing:-0.5px; margin-top:6px;">{implied_str}</div>'
        f'<div style="color:#6B7280; font-size:11px; margin-top:8px;">'
        f'Historical 5y CAGR: <span style="color:#9CA3AF;">{hist_str}</span>'
        f'</div>'
        f'<div style="color:{gap_color}; font-size:13px; font-weight:600; '
        f'margin-top:4px;">Gap: {gap_text}</div>'
        f'<div style="color:#9CA3AF; font-size:11px; line-height:1.5; '
        f'margin-top:10px;">{interpretation}</div>'
        f'</div>'
    )


def render_reverse_dcf_spread(bundles: dict, prices: dict,
                               waccs: dict) -> None:
    """Args:
      bundles: ticker -> HydratedBundle
      prices:  ticker -> current price (float)
      waccs:   ticker -> WACC (decimal, e.g. 0.10)
    """
    if not bundles:
        st.info("Reverse DCF needs at least one ticker.")
        return

    tickers = list(bundles.keys())
    cols = st.columns(len(tickers))

    for col, ticker in zip(cols, tickers):
        bundle = bundles[ticker]
        price = prices.get(ticker)
        wacc = waccs.get(ticker, 0.10)

        if (bundle is None or bundle.income.empty
                or not price or price <= 0):
            col.markdown(
                _card_html(
                    ticker=ticker, implied=None, historical=None,
                    gap_color="#6B7280", gap_text="—",
                    interpretation="",
                    error="Missing price or financials — reverse DCF skipped.",
                ),
                unsafe_allow_html=True,
            )
            continue

        try:
            from valuation.reverse_dcf import run_reverse_dcf
            res = run_reverse_dcf(
                income=bundle.income,
                balance=bundle.balance,
                cash=bundle.cash,
                target_price=float(price),
                wacc=float(wacc),
            )
        except Exception as exc:
            col.markdown(
                _card_html(
                    ticker=ticker, implied=None, historical=None,
                    gap_color="#6B7280", gap_text="—",
                    interpretation="",
                    error=f"Reverse DCF failed: {type(exc).__name__}",
                ),
                unsafe_allow_html=True,
            )
            continue

        if res is None or res.implied_growth is None:
            col.markdown(
                _card_html(
                    ticker=ticker, implied=None,
                    historical=res.historical_growth if res else None,
                    gap_color="#6B7280", gap_text="—",
                    interpretation="",
                    error=(res.error if res and res.error
                            else "Implied growth outside ±50% bracket."),
                ),
                unsafe_allow_html=True,
            )
            continue

        implied = float(res.implied_growth)
        historical = res.historical_growth
        if historical is not None and np.isfinite(historical):
            gap_pp = (implied - historical) * 100.0
            gap_text = f"{gap_pp:+.1f}pp"
            gap_color = _gap_color(gap_pp)
        else:
            gap_pp = 0.0
            gap_text = "n/a (no history)"
            gap_color = "#6B7280"

        col.markdown(
            _card_html(
                ticker=ticker, implied=implied,
                historical=historical,
                gap_color=gap_color, gap_text=gap_text,
                interpretation=res.interpretation or "",
            ),
            unsafe_allow_html=True,
        )

    st.caption(
        "Each card solves for the stage-1 growth rate that justifies the "
        "current share price under that ticker's WACC. Gap = implied minus "
        "historical 5y revenue CAGR (in pp). Green <1pp, gold 1-3pp, "
        "copper >3pp."
    )
