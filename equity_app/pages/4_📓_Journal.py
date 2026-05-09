"""
Journal — decision log + thesis review.

Two sections:
- New entry form (ticker, action, thesis, exit criteria, price snapshot)
- List of decisions (filter by ticker / status; close or cancel any open one)

Closing a decision records the exit price + outcome notes — the row is
preserved (no hard delete) so the audit trail stays intact.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from data.decision_journal_db import (
    Decision, add_decision, list_decisions, close_decision, delete_decision,
)


# ============================================================
# Header
# ============================================================
st.markdown(
    '<div class="eq-section-label">📓 DECISION JOURNAL</div>',
    unsafe_allow_html=True,
)
st.caption(
    "Record buy / sell / hold / watch decisions with the thesis behind "
    "each. Six months later, re-read and judge whether the thesis "
    "played out — or whether you got lucky."
)


# ============================================================
# New entry form
# ============================================================
with st.expander("➕ New decision", expanded=False):
    with st.form("new_decision"):
        c1, c2, c3 = st.columns([1.5, 1, 1])
        ticker = c1.text_input("Ticker", placeholder="AAPL").upper().strip()
        action = c2.selectbox(
            "Action", ["buy", "sell", "hold", "watch"], index=0,
        )
        conviction = int(c3.select_slider(
            "Conviction (1=low, 5=high)",
            options=[1, 2, 3, 4, 5], value=3,
        ))

        c4, c5 = st.columns(2)
        price = c4.number_input(
            "Price at decision ($)", min_value=0.0,
            value=0.0, step=0.01, format="%.2f",
        )
        intrinsic = c5.number_input(
            "Estimated intrinsic ($)", min_value=0.0,
            value=0.0, step=0.01, format="%.2f",
            help="Optional — your fair-value estimate at decision time.",
        )

        thesis = st.text_area(
            "Thesis · *why* are you doing this?",
            placeholder="E.g. Services revenue inflection + buybacks compound. "
                        "10-year IRR target ~12% from here.",
            height=110,
        )
        exit_criteria = st.text_area(
            "Exit criteria · *what* would invalidate the thesis?",
            placeholder="E.g. Services growth <8% for 2 consecutive quarters. "
                        "OR Apple-loyalty scores drop. OR DOJ break-up materially advances.",
            height=80,
        )

        submitted = st.form_submit_button("Save decision", type="primary")
        if submitted:
            if not ticker:
                st.error("Ticker is required.")
            elif not thesis.strip():
                st.error("Thesis is required — the whole point is to write it down.")
            else:
                did = add_decision(
                    ticker=ticker, action=action,
                    thesis=thesis.strip(),
                    exit_criteria=exit_criteria.strip(),
                    price_at_decision=float(price) if price > 0 else None,
                    intrinsic_at_decision=float(intrinsic) if intrinsic > 0 else None,
                    conviction=conviction,
                )
                st.success(f"Saved decision #{did} for {ticker}.")
                st.rerun()


# ============================================================
# Filters
# ============================================================
fc1, fc2, _ = st.columns([1.5, 1.5, 5])
with fc1:
    filter_ticker = st.text_input(
        "Filter by ticker", "",
        placeholder="Leave blank for all", key="journal_filter_ticker",
    ).upper().strip() or None
with fc2:
    filter_status = st.selectbox(
        "Status", ["all", "open", "closed", "cancelled"], index=1,
        key="journal_filter_status",
    )


# ============================================================
# Decisions list
# ============================================================
decisions = list_decisions(
    ticker=filter_ticker,
    status=filter_status if filter_status != "all" else None,
    limit=200,
)

if not decisions:
    st.info(
        "No decisions match the current filters. Add one above to start "
        "the journal."
    )
    st.stop()


def _glyph(action: str) -> str:
    return {"buy": "🟢", "sell": "🔴", "hold": "🟡", "watch": "👁"}.get(action, "·")


def _conv_dots(c) -> str:
    return ("●" * int(c) + "○" * (5 - int(c))) if c else "—"


# ----- Summary count strip -----
opens = [d for d in decisions if d.status == "open"]
closes = [d for d in decisions if d.status == "closed"]
cancels = [d for d in decisions if d.status == "cancelled"]
sc1, sc2, sc3 = st.columns(3)
sc1.metric("Open",      len(opens))
sc2.metric("Closed",    len(closes))
sc3.metric("Cancelled", len(cancels))


# ----- One expander per decision (open ones expanded by default) -----
st.markdown(
    '<div class="eq-section-label" style="margin-top:14px;">DECISIONS</div>',
    unsafe_allow_html=True,
)

for d in decisions:
    summary = (
        f"{_glyph(d.action)} **{d.ticker}** · {d.action.upper()} · "
        f"{d.decided_at[:10]} · {_conv_dots(d.conviction)} · "
        f"_{d.status}_"
    )
    with st.expander(summary, expanded=(d.status == "open")):
        # --- Thesis + criteria ---
        cc1, cc2 = st.columns(2)
        with cc1:
            st.markdown("**Thesis**")
            st.markdown(d.thesis or "_(empty)_")
        with cc2:
            st.markdown("**Exit criteria**")
            st.markdown(d.exit_criteria or "_(none specified)_")

        # --- Snapshot at decision time ---
        snap_row = []
        if d.price_at_decision is not None:
            snap_row.append(f"Price ${d.price_at_decision:.2f}")
        if d.intrinsic_at_decision is not None:
            snap_row.append(f"Intrinsic ${d.intrinsic_at_decision:.2f}")
            if d.price_at_decision and d.price_at_decision > 0:
                gap = (d.intrinsic_at_decision / d.price_at_decision - 1) * 100
                snap_row.append(f"MoS {gap:+.1f}%")
        if snap_row:
            st.caption(" · ".join(snap_row))

        # --- Outcome (closed) ---
        if d.status == "closed":
            outc = []
            if d.exit_price is not None:
                outc.append(f"Exit ${d.exit_price:.2f}")
                if d.price_at_decision and d.price_at_decision > 0:
                    ret_pct = (d.exit_price / d.price_at_decision - 1) * 100
                    outc.append(f"Return {ret_pct:+.1f}%")
            if d.closed_at:
                outc.append(f"Closed {d.closed_at[:10]}")
            if outc:
                st.markdown("**Outcome:** " + " · ".join(outc))
            if d.outcome_notes:
                st.caption(f"Notes: {d.outcome_notes}")

        # --- Actions on the open ones ---
        if d.status == "open":
            ac1, ac2, ac3 = st.columns([2, 2, 1])
            with ac1:
                exit_p = st.number_input(
                    "Exit price",
                    min_value=0.0, value=0.0, step=0.01, format="%.2f",
                    key=f"exit_p_{d.id}",
                )
            with ac2:
                notes = st.text_input(
                    "Outcome notes", "",
                    placeholder="Took profit / stopped out / thesis broke …",
                    key=f"notes_{d.id}",
                )
            with ac3:
                if st.button("Close", key=f"close_{d.id}", type="primary",
                             use_container_width=True):
                    close_decision(
                        d.id,
                        exit_price=float(exit_p) if exit_p > 0 else None,
                        outcome_notes=notes.strip(), status="closed",
                    )
                    st.rerun()

            cd1, cd2 = st.columns([1, 5])
            with cd1:
                if st.button("Cancel", key=f"cancel_{d.id}",
                             use_container_width=True):
                    close_decision(d.id, outcome_notes="cancelled",
                                    status="cancelled")
                    st.rerun()
            with cd2:
                if st.button("🗑 Delete (cannot undo)",
                             key=f"delete_{d.id}", type="secondary"):
                    delete_decision(d.id)
                    st.rerun()
