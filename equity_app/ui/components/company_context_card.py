"""
Compact "Company Context" card — a one-glance summary at the top of the
Overview tab. Larger than a chip strip, smaller than the full Company
Profile section below.

Shows:
- Company name (big) + ticker
- Sector › Industry breadcrumb
- Description preview (truncated to ~280 chars)
- Up to 5 peer chips (clickable would require st.button per chip — kept
  as static chips here; the Peers tab is the place for navigation).

All HTML is emitted as single-line concatenated strings to avoid the
Streamlit markdown ≥4-space-indent code-block trap.
"""
from __future__ import annotations
from typing import Iterable, Optional


import streamlit as st


def _truncate(text: str, max_chars: int = 280) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:") + "…"


def _peer_chip(symbol: str) -> str:
    return (
        '<span style="display:inline-block; padding:4px 10px; '
        'margin:0 6px 6px 0; border:1px solid var(--border); '
        'border-radius:14px; font-size:11px; font-weight:600; '
        'color:var(--text-secondary); letter-spacing:0.4px; '
        'background:var(--surface-2);">'
        f'{symbol}'
        '</span>'
    )


def render_company_context_card(
    *,
    ticker: str,
    name: Optional[str],
    sector: Optional[str],
    industry: Optional[str],
    description: Optional[str],
    peers: Optional[Iterable[str]] = None,
) -> None:
    """Render the prominent company-context card.

    `peers` is an iterable of plain ticker strings; pass `[p.ticker for
    p in peers_demo]` from the page.
    """
    display_name = name or ticker
    breadcrumb_parts = [p for p in (sector, industry) if p]
    breadcrumb = (
        " <span style=\"color:var(--text-muted);\">›</span> ".join(
            f'<span style="color:var(--text-secondary);">{p}</span>'
            for p in breadcrumb_parts
        )
        if breadcrumb_parts
        else '<span style="color:var(--text-muted);">Sector unavailable</span>'
    )

    desc = _truncate(description or "", max_chars=320)
    desc_html = (
        '<div style="color:var(--text-secondary); font-size:13px; '
        'line-height:1.55; margin-top:10px;">'
        f'{desc}'
        '</div>'
    ) if desc else ""

    peer_list = [p for p in (peers or []) if p and p != ticker][:5]
    peers_html = ""
    if peer_list:
        chips = "".join(_peer_chip(p) for p in peer_list)
        peers_html = (
            '<div style="margin-top:14px;">'
            '<div style="font-size:11px; letter-spacing:0.4px; '
            'text-transform:uppercase; color:var(--text-muted); '
            'margin-bottom:6px;">PEERS</div>'
            f'<div>{chips}</div>'
            '</div>'
        )

    html = (
        '<div class="eq-card" style="padding:20px 22px;">'
        '<div style="display:flex; align-items:baseline; '
        'justify-content:space-between; gap:12px; flex-wrap:wrap;">'
        '<div>'
        f'<div style="font-size:22px; font-weight:600; '
        f'color:var(--text-primary); line-height:1.2;">{display_name}</div>'
        f'<div style="font-size:12px; letter-spacing:0.6px; '
        f'color:var(--text-muted); margin-top:4px;">{ticker}</div>'
        '</div>'
        '<div style="font-size:12px; text-align:right;">'
        f'{breadcrumb}'
        '</div>'
        '</div>'
        f'{desc_html}'
        f'{peers_html}'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)
