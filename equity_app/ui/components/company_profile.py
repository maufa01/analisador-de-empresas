"""
Company-profile section — 2-column layout (overview + key executives).

Hydrates from live providers (FMP profile + yfinance .info), falling
back to the legacy hardcoded ``data.company_profiles`` map ONLY when
no live data was passed in. The hardcoded dict covered three tickers
(AAPL / MSFT / JPM); the live path covers any ticker yfinance / FMP
can resolve.

All HTML emitted as single-line, no-leading-whitespace strings to
avoid the Streamlit markdown indented-code-block trap.
"""
from __future__ import annotations
from typing import Optional

import streamlit as st


# ============================================================
# Render helpers
# ============================================================
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


# ============================================================
# Profile + executive merging
# ============================================================
def _strip_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    return (url.replace("https://", "")
              .replace("http://", "")
              .rstrip("/"))


def _format_hq(city, state, country) -> Optional[str]:
    parts = [p for p in (city, state, country) if p]
    return ", ".join(parts) if parts else None


def _ceo_from_yf_officers(info: dict) -> Optional[str]:
    """yfinance puts officers in info['companyOfficers']."""
    officers = info.get("companyOfficers") or []
    for o in officers:
        title = (o.get("title") or "").lower()
        if "chief executive" in title or "ceo" in title:
            return o.get("name")
    return None


def _merge_profile_sources(
    ticker: str,
    fmp_profile: Optional[dict],
    live_info: Optional[dict],
) -> dict:
    """Merge FMP and yfinance profile data — FMP wins on conflict."""
    out: dict = {"ticker": ticker, "name": ticker}

    if live_info:
        out.update({
            "name":       (live_info.get("longName")
                           or live_info.get("shortName")
                           or live_info.get("name")),
            "description": live_info.get("longBusinessSummary")
                           or live_info.get("description"),
            "ceo":         _ceo_from_yf_officers(live_info),
            "website":     _strip_url(live_info.get("website")),
            "exchange":    live_info.get("exchange"),
            "sector":      live_info.get("sector"),
            "industry":    live_info.get("industry"),
            "employees":   live_info.get("fullTimeEmployees")
                           or live_info.get("employees"),
            "headquarters": _format_hq(
                live_info.get("city"),
                live_info.get("state"),
                live_info.get("country"),
            ),
        })

    if fmp_profile:
        if fmp_profile.get("description"):
            out["description"] = fmp_profile["description"]
        if fmp_profile.get("ceo"):
            out["ceo"] = fmp_profile["ceo"]
        if fmp_profile.get("ipoDate"):
            year = str(fmp_profile["ipoDate"])[:4]
            out["founded"] = f"IPO {year}" if year else None
        if fmp_profile.get("fullTimeEmployees"):
            try:
                out["employees"] = int(fmp_profile["fullTimeEmployees"])
            except (TypeError, ValueError):
                pass
        if fmp_profile.get("city"):
            out["headquarters"] = _format_hq(
                fmp_profile.get("city"),
                fmp_profile.get("state"),
                fmp_profile.get("country"),
            )
        if fmp_profile.get("website"):
            out["website"] = _strip_url(fmp_profile["website"])
        if fmp_profile.get("exchangeShortName"):
            out["exchange"] = fmp_profile["exchangeShortName"]
        if fmp_profile.get("sector"):
            out["sector"] = fmp_profile["sector"]
        if fmp_profile.get("industry"):
            out["industry"] = fmp_profile["industry"]

    return {k: v for k, v in out.items() if v not in (None, "")}


def _executives_from_live(
    fmp_profile: Optional[dict],
    live_info: Optional[dict],
) -> list[dict]:
    """yfinance ``companyOfficers`` is the only live source we have for
    executives today; FMP /key_executives needs paid tier."""
    if live_info and live_info.get("companyOfficers"):
        out: list[dict] = []
        for o in live_info["companyOfficers"][:6]:
            name = o.get("name")
            role = o.get("title")
            if not name or not role:
                continue
            out.append({"name": name, "role": role, "since": None})
        return out
    return []


def _legacy_fallback(ticker: str) -> tuple[Optional[dict], list[dict]]:
    """Removed — the FMP → yfinance chain in ``data_adapter`` covers
    every ticker now. Kept as a stub so callers don't need to change."""
    return None, []


# ============================================================
# Public entry
# ============================================================
def render_company_profile(
    ticker: str,
    live_info: Optional[dict] = None,
    fmp_profile: Optional[dict] = None,
) -> None:
    """Render company overview + key executives.

    Sources priority:
    1. ``fmp_profile`` (CEO, description, employees, founded)
    2. ``live_info`` (yfinance ``.info``)
    3. legacy ``data/company_profiles.py`` map (only AAPL / MSFT / JPM)
    """
    profile = _merge_profile_sources(ticker, fmp_profile, live_info)
    executives = _executives_from_live(fmp_profile, live_info)

    # Fall through to the legacy hardcoded map only when both live
    # sources came back empty.
    if (not profile or len(profile) <= 2) and not executives:
        legacy_profile, legacy_executives = _legacy_fallback(ticker)
        if legacy_profile:
            profile = {**profile, **legacy_profile}
        if legacy_executives:
            executives = legacy_executives

    if not profile and not executives:
        st.markdown(
            '<div class="eq-card" style="padding:18px; '
            'color:var(--text-muted); font-size:12px;">'
            f'No company profile available for <b>{ticker}</b>.'
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

            employees = profile.get("employees")
            employees_str = (f"{int(employees):,}"
                             if employees and isinstance(employees, (int, float))
                             else None)

            kv_html = "".join([
                _kv_row("CEO",              ceo_full),
                _kv_row("CFO",              profile.get("cfo")),
                _kv_row("Founded",          profile.get("founded")),
                _kv_row("Headquarters",     profile.get("headquarters")),
                _kv_row("Employees",        employees_str),
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
