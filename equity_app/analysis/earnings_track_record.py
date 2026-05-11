"""
Earnings track record — recent EPS beats / misses + next earnings date.

Sources from yfinance's ``Ticker(symbol).earnings_history`` and
``Ticker(symbol).calendar`` endpoints. yfinance only provides the last
~4 quarters, which is enough to spot a recent pattern (consistent
beats vs trending misses). For 16+ quarters of history wire FMP later.

Returns the empty result silently when yfinance can't resolve the
ticker — the UI renders a "data unavailable" placeholder.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import math
import numpy as np
import pandas as pd
import streamlit as st

from data.market_data import _yfinance


@dataclass
class EarningsHistory:
    quarters:        pd.DataFrame                    # one row per quarter
    beat_rate:       Optional[float] = None          # 0.0 - 1.0
    avg_surprise:    Optional[float] = None          # %
    median_surprise: Optional[float] = None
    consistency:     str = "—"                       # high / medium / low
    next_date:       Optional[str] = None
    eps_estimate:    Optional[float] = None
    revenue_estimate: Optional[float] = None
    note:            str = ""


# ============================================================
# Internals
# ============================================================
def _coerce_history_df(raw) -> pd.DataFrame:
    """yfinance returns either a DataFrame or None depending on version."""
    if raw is None:
        return pd.DataFrame()
    if not isinstance(raw, pd.DataFrame) or raw.empty:
        return pd.DataFrame()

    df = raw.copy()
    # Normalise column names — yfinance has shipped both camelCase and
    # spaced variants over the years.
    rename = {
        "epsActual":    "eps_actual",
        "epsEstimate":  "eps_estimate",
        "EPS Actual":   "eps_actual",
        "EPS Estimate": "eps_estimate",
        "epsDifference": "eps_diff",
        "surprisePercent": "surprise_pct",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    # Compute surprise + surprise_pct from raw inputs. We always
    # recompute even when yfinance ships ``surprisePercent`` because
    # the convention has drifted across yfinance versions (sometimes
    # decimal 0.20, sometimes pct 20.0). Computing from eps_actual −
    # eps_estimate guarantees one consistent unit (pct, e.g. 20.0).
    if "eps_actual" in df.columns and "eps_estimate" in df.columns:
        df["surprise"] = df["eps_actual"] - df["eps_estimate"]
        df["beat"] = df["eps_actual"] > df["eps_estimate"]
        df["surprise_pct"] = (
            (df["eps_actual"] - df["eps_estimate"]).abs()
            .where(df["eps_estimate"].abs() > 0)
            / df["eps_estimate"].abs() * 100.0
            * np.sign(df["eps_actual"] - df["eps_estimate"])
        )
    return df.sort_index(ascending=False)


def _consistency_label(beat_rate: Optional[float], surprise_std: Optional[float]) -> str:
    if beat_rate is None:
        return "—"
    if beat_rate >= 0.75 and (surprise_std is None or surprise_std < 5.0):
        return "high"
    if beat_rate >= 0.50:
        return "medium"
    return "low"


# ============================================================
# Public API
# ============================================================
def _from_fmp_extended(ticker: str) -> Optional[EarningsHistory]:
    """16+ quarters from FMP when ``FMP_API_KEY`` is set. Returns None
    silently if the key isn't configured or the request fails."""
    try:
        from data import fmp_extras
    except Exception:
        return None
    if not fmp_extras.is_available():
        return None
    raw = fmp_extras.fetch_earnings_history(ticker, limit=20)
    if raw is None or raw.empty:
        return None
    df = raw.copy()
    if "epsActual" in df.columns:
        df = df.rename(columns={
            "epsActual":         "eps_actual",
            "epsEstimated":      "eps_estimate",
            "eps_surprise":      "surprise",
            "eps_surprise_pct":  "surprise_pct",
            "beat_eps":          "beat",
        })
    if "date" in df.columns:
        df = df.set_index("date").sort_index(ascending=False)

    beat_rate = avg = med = std = None
    if "beat" in df.columns:
        beats = int(df["beat"].dropna().sum())
        total = int(df["beat"].dropna().count())
        beat_rate = beats / total if total else None
    if "surprise_pct" in df.columns:
        sp = df["surprise_pct"].dropna()
        if not sp.empty:
            avg = float(sp.mean())
            med = float(sp.median())
            std = float(sp.std(ddof=1)) if len(sp) > 1 else None

    return EarningsHistory(
        quarters=df,
        beat_rate=beat_rate,
        avg_surprise=avg,
        median_surprise=med,
        consistency=_consistency_label(beat_rate, std),
        next_date=None, eps_estimate=None, revenue_estimate=None,
        note=f"{len(df)}-quarter history from FMP.",
    )


@st.cache_data(ttl=21_600, show_spinner=False)
def get_earnings_history(ticker: str) -> EarningsHistory:
    """
    Prefers FMP (16+ quarters) when the API key is configured. Falls back
    to yfinance (last ~4 quarters) when FMP is unavailable.
    """
    fmp_result = _from_fmp_extended(ticker)
    if fmp_result is not None:
        return fmp_result

    yf = _yfinance()
    if yf is None or not ticker:
        return EarningsHistory(quarters=pd.DataFrame(),
                                note="yfinance unavailable")

    try:
        t = yf.Ticker(ticker)
    except Exception as e:
        return EarningsHistory(quarters=pd.DataFrame(),
                                note=f"yfinance error: {e}")

    # ---- Earnings history (last ~4 quarters) ----
    raw_history = None
    for attr in ("earnings_history", "earnings_dates"):
        try:
            raw_history = getattr(t, attr, None)
            if raw_history is not None and not getattr(raw_history, "empty", True):
                break
        except Exception:
            continue

    df = _coerce_history_df(raw_history)
    beat_rate = avg_surprise = median_surprise = None
    surprise_std = None
    if not df.empty and "beat" in df.columns:
        beats = int(df["beat"].sum())
        total = int(df["beat"].count())
        beat_rate = beats / total if total else None
    if not df.empty and "surprise_pct" in df.columns:
        sp = df["surprise_pct"].dropna()
        if not sp.empty:
            avg_surprise = float(sp.mean())
            median_surprise = float(sp.median())
            surprise_std = float(sp.std(ddof=1)) if len(sp) > 1 else None

    # ---- Next earnings + estimate ----
    next_date = None
    eps_est = None
    rev_est = None

    def _format_earnings_date(raw) -> Optional[str]:
        """yfinance now ships Earnings Date as a list[datetime] (one or
        two entries — typically [start, end] of the announcement window).
        Pre-2024 it was a single date or a string. Normalise to an ISO
        'YYYY-MM-DD' string so the UI can slice [:10] safely."""
        if raw is None:
            return None
        # Unwrap a list/tuple to its first element
        if isinstance(raw, (list, tuple)):
            if not raw:
                return None
            raw = raw[0]
        # pandas Timestamp / datetime / date → ISO
        if hasattr(raw, "strftime"):
            try:
                return raw.strftime("%Y-%m-%d")
            except Exception:
                pass
        # Numpy datetime64 / pandas NaT
        try:
            ts = pd.Timestamp(raw)
            if pd.isna(ts):
                return None
            return ts.strftime("%Y-%m-%d")
        except Exception:
            pass
        # Fallback: stringify and slice — at least won't print "[datetime("
        s = str(raw).strip()
        return s[:10] if s else None

    try:
        cal = getattr(t, "calendar", None)
        if cal is not None:
            if hasattr(cal, "empty") and not cal.empty:
                # DataFrame variant
                if "Earnings Date" in cal.index:
                    next_date = _format_earnings_date(
                        cal.loc["Earnings Date"].iloc[0]
                    )
                if "Earnings Estimate" in cal.index:
                    val = cal.loc["Earnings Estimate"].iloc[0]
                    eps_est = float(val) if pd.notna(val) else None
                if "Revenue Estimate" in cal.index:
                    val = cal.loc["Revenue Estimate"].iloc[0]
                    rev_est = float(val) if pd.notna(val) else None
            elif isinstance(cal, dict):
                next_date = _format_earnings_date(cal.get("Earnings Date"))
                eps_est = (float(cal["Earnings Estimate"])
                           if cal.get("Earnings Estimate") is not None else None)
                rev_est = (float(cal["Revenue Estimate"])
                           if cal.get("Revenue Estimate") is not None else None)
    except Exception:
        pass

    return EarningsHistory(
        quarters=df,
        beat_rate=beat_rate,
        avg_surprise=avg_surprise,
        median_surprise=median_surprise,
        consistency=_consistency_label(beat_rate, surprise_std),
        next_date=next_date,
        eps_estimate=eps_est,
        revenue_estimate=rev_est,
        note=("" if not df.empty
              else "No quarterly history returned by yfinance"),
    )
