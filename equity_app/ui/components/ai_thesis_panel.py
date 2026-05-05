"""
AI thesis panel — offline mode (copy-paste). Generates the prompt
on demand and exposes it in a textarea the user can copy and paste
into Claude.ai or ChatGPT.

When ``ANTHROPIC_API_KEY`` is later configured the same component will
flip to "send and stream" — the prompt builder underneath is unchanged.
"""
from __future__ import annotations

import streamlit as st

from analysis.ai_thesis_prompt import ThesisPrompt


def render_ai_thesis_panel(prompt: ThesisPrompt, *, ticker: str) -> None:
    st.markdown(
        '<div class="eq-card" style="padding:18px 22px; '
        'border-left:4px solid var(--accent);">'
        '<div class="eq-section-label">AI INVESTMENT THESIS · OFFLINE MODE</div>'
        '<div style="margin-top:8px; color:var(--text-secondary); '
        'font-size:13px; line-height:1.5;">'
        'Bundles every result on this page (DCF, score, EQ, balance-sheet '
        'forensics, stress tests, etc.) into a structured prompt. Paste it '
        'into Claude.ai or ChatGPT to get an institutional-quality thesis '
        'grounded in the analysis. When an API key is wired, the same '
        'prompt fires automatically.'
        '</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4, gap="small")
    c1.metric("CHARS", f"{prompt.n_chars:,}")
    c2.metric("WORDS", f"{prompt.n_words:,}")
    c3.metric("~INPUT TOKENS", f"{prompt.estimated_input_tokens:,}")
    c4.metric("~SONNET COST", f"${prompt.estimated_cost_sonnet_usd:.4f}")

    st.text_area(
        "Prompt — select all (Ctrl/⌘+A) then copy (Ctrl/⌘+C):",
        value=prompt.prompt,
        height=320,
        key=f"ai_thesis_text_{ticker}",
    )
    st.caption(
        "Token estimate uses 4-chars-per-token (Claude tokeniser averages ~3.5 — "
        "the estimate is mildly conservative). Cost shown covers input only; "
        "Sonnet output runs at $15/Mtok."
    )
