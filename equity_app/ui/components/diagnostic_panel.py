"""
Diagnostic panel — shows the session-scoped API request log + a
provider-status snapshot. Lives in a tab on the Macro page so it's
discoverable but doesn't clutter the main analysis flow.
"""
from __future__ import annotations
from typing import Optional

import pandas as pd
import streamlit as st


_DOWNSIDE = "rgba(184,115,51,1)"


def _summary_metrics(df: pd.DataFrame) -> None:
    total = len(df)
    cached = int(df["cached"].sum()) if "cached" in df.columns else 0
    failed = int((~df["success"]).sum()) if "success" in df.columns else 0
    success_rate = ((total - failed) / total * 100) if total else 0.0

    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.metric("TOTAL CALLS", str(total))
    c2.metric("CACHED",
              str(cached),
              f"{cached/total*100:.0f}%" if total else "")
    c3.metric("FAILED", str(failed))
    c4.metric("SUCCESS RATE", f"{success_rate:.0f}%")


def _format_log_for_display(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "timestamp" in out.columns:
        out["time"] = out["timestamp"].apply(
            lambda x: x.strftime("%H:%M:%S") if pd.notna(x) else "—"
        )
        out = out.drop(columns=["timestamp"])
    if "response_time_ms" in out.columns:
        out["response_time_ms"] = out["response_time_ms"].apply(
            lambda v: f"{int(v)}ms" if isinstance(v, (int, float)) and pd.notna(v) else "—"
        )
    if "success" in out.columns:
        out["success"] = out["success"].map({True: "✓", False: "✗"})
    if "cached" in out.columns:
        out["cached"] = out["cached"].map({True: "cached", False: "fresh"})

    front = ["time", "provider", "endpoint", "ticker", "success",
             "cached", "response_time_ms"]
    cols = [c for c in front if c in out.columns]
    cols += [c for c in out.columns if c not in cols]
    return out[cols]


def render_diagnostic_panel() -> None:
    st.markdown(
        '<div class="eq-section-label">API DIAGNOSTICS · SESSION</div>',
        unsafe_allow_html=True,
    )

    # ---- Health snapshot ----
    if "_api_status" in st.session_state and st.session_state["_api_status"]:
        st.markdown(
            '<div class="eq-section-label" style="margin-top:12px;">'
            'PROVIDER HEALTH SNAPSHOT</div>',
            unsafe_allow_html=True,
        )
        rows = []
        for provider, info in (st.session_state["_api_status"] or {}).items():
            rows.append({
                "Provider":   provider,
                "Status":     info.get("status", "—"),
                "Reason":     info.get("reason", "") or "",
                "Fetched at": (info.get("fetched_at").astimezone().strftime("%H:%M:%S")
                                if info.get("fetched_at") else "—"),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                     use_container_width=True)

    # ---- Session log ----
    from utils.api_logger import get_log, clear_log
    log = get_log()
    if not log:
        st.markdown(
            '<div class="eq-card" style="padding:14px 18px; '
            'color:var(--text-muted); font-size:13px; margin-top:10px;">'
            'No API calls logged yet in this session. As pages fetch data, '
            'each external request lands here.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    df = pd.DataFrame(log)
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    _summary_metrics(df)

    st.markdown(
        '<div class="eq-section-label" style="margin-top:14px;">'
        f'RECENT CALLS · LAST {min(len(df), 50)}</div>',
        unsafe_allow_html=True,
    )
    st.dataframe(_format_log_for_display(df.tail(50)),
                 hide_index=True, use_container_width=True)

    # ---- Errors detail ----
    errors = df[~df["success"]] if "success" in df.columns else pd.DataFrame()
    if not errors.empty:
        st.markdown(
            '<div class="eq-section-label" style="margin-top:14px;">'
            f'RECENT ERRORS · {len(errors)}</div>',
            unsafe_allow_html=True,
        )
        for _, row in errors.tail(10).iterrows():
            with st.expander(
                f"{row.get('provider', '?')}/{row.get('endpoint', '?')} "
                f"· {row.get('ticker') or 'n/a'}",
                expanded=False,
            ):
                err = row.get("error") or "No error message captured."
                st.code(str(err))

    if st.button("Clear session log", key="diag_clear_log",
                 use_container_width=False):
        clear_log()
        st.rerun()
