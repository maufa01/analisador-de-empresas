"""
Company profile section — 2-column layout (overview + key executives).

Reads from the hardcoded ``data.company_profiles`` map until the live
FMP provider's profile / executives endpoints are wired in. Renders a
clean fallback message when the ticker is outside the curated set.

All HTML emitted as single-line, no-leading-whitespace strings to
avoid the markdown indented-code-block trap.
"""
from __future__ import annotations
from typing import Optional

import streamlit as st

from data.company_profiles import get_company_profile, get_executives


def _kv_row(label: str, value) -> str:
    if value is None or value == "":
        return ""
    return (
        '<div style="display:flex; justify-content:space-between; '
        'padding:6px 0; border-bottom:1px solid var(--border); font-size:13px;">'
        f'<span style="color:var(--text-muted); letter-spacing:0.4px; '
        f'text-transform:uppercase; font-size:11px;">{label}</span>'
        f'<span style="color:var(--text-primary); font-weight:500; '
        f'font-variant-numeric:tabular-nums;">{value}</span>'
        '</div>'
    )


def _exec_row(name: str, role: str, since: Optional[int]) -> str:
    since_html = (f'<span style="color:var(--text-muted); font-size:11px;">'
                  f'Since {since}</span>' if since else '')
    return (
        '<div style="display:grid; grid-template-columns: 1.1fr 1.5fr 0.7fr; '
        'gap:8px; padding:8px 0; border-bottom:1px solid var(--border); '
        'font-size:13px; align-items:baseline;">'
        f'<span style="color:var(--text-primary); font-weight:500;">{name}</span>'
        f'<span style="color:var(--text-secondary);">{role}</span>'
        f'<span style="text-align:right;">{since_html}</span>'
        '</div>'
    )


def render_company_profile(ticker: str) -> None:
    profile = get_company_profile(ticker)
    executives = get_executives(ticker)

    if not profile and not executives:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:12px;">'
            f'Company profile and key-executive data for <b>{ticker}</b> '
            'will populate once the FMP provider is wired in.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    left, right = st.columns([3, 2], gap="medium")

    # ---- LEFT: Company Overview ----
    with left:
        st.markdown(
            '<div class="eq-section-label">COMPANY OVERVIEW</div>',
            unsafe_allow_html=True,
        )
        if profile:
            description = profile.get("description") or ""
            ceo_full = profile.get("ceo")
            if ceo_full and profile.get("ceo_since"):
                ceo_full = f"{ceo_full} (since {profile['ceo_since']})"

            kv_html = "".join([
                _kv_row("CEO",              ceo_full),
                _kv_row("CFO",              profile.get("cfo")),
                _kv_row("Founded",          profile.get("founded")),
                _kv_row("Headquarters",     profile.get("headquarters")),
                _kv_row("Employees",
                        f'{profile["employees"]:,}'
                        if profile.get("employees") else None),
                _kv_row("Website",          profile.get("website")),
                _kv_row("Exchange",         profile.get("exchange")),
                _kv_row("Sector",           profile.get("sector")),
                _kv_row("Industry",         profile.get("industry")),
                _kv_row("Fiscal year end",  profile.get("fiscal_year_end")),
            ])

            description_html = (
                f'<div style="color:var(--text-secondary); font-size:13px; '
                f'line-height:1.5; margin-bottom:14px;">{description}</div>'
                if description else ""
            )
            st.markdown(
                '<div class="eq-card" style="padding:18px;">'
                + description_html
                + '<div style="display:flex; flex-direction:column;">'
                + kv_html
                + '</div></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="eq-card" style="padding:18px; '
                'color:var(--text-muted); font-size:12px;">'
                'Profile not available for this ticker.'
                '</div>',
                unsafe_allow_html=True,
            )

    # ---- RIGHT: Key Executives ----
    with right:
        st.markdown(
            '<div class="eq-section-label">KEY EXECUTIVES</div>',
            unsafe_allow_html=True,
        )
        if executives:
            rows_html = "".join(
                _exec_row(e["name"], e["role"], e.get("since"))
                for e in executives
            )
            st.markdown(
                '<div class="eq-card" style="padding:18px;">'
                + rows_html +
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="eq-card" style="padding:18px; '
                'color:var(--text-muted); font-size:12px;">'
                'Executive roster not available for this ticker.'
                '</div>',
                unsafe_allow_html=True,
            )
