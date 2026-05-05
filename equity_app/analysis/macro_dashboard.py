"""
Macro overlay — yields curve / VIX / DXY / HY-spreads → regime call.

Why no FRED here: a FRED API key is not deployable to Streamlit Cloud
without secret config. We use yfinance proxies for the same series:

    ^IRX  → 13-week T-bill yield (≈3M)
    ^FVX  → 5Y Treasury yield
    ^TNX  → 10Y Treasury yield
    ^TYX  → 30Y Treasury yield
    ^VIX  → equity vol index
    DX-Y.NYB → US Dollar Index
    HYG, LQD → HY/IG corporate bond ETF spread proxy

When FRED is wired later, swap the inner helpers without changing the
result dataclass or callers.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import logging
import pandas as pd

logger = logging.getLogger(__name__)


# ============================================================
# Result dataclasses
# ============================================================
@dataclass
class MacroRegime:
    label: str                                 # RISK-ON / NEUTRAL / CAUTIOUS / RISK-OFF
    flag: str                                  # green / yellow / red
    score: int
    reasons: list[str] = field(default_factory=list)


@dataclass
class MacroSnapshot:
    available: bool
    timestamp: pd.Timestamp

    yield_3m:  Optional[float] = None
    yield_2y:  Optional[float] = None
    yield_5y:  Optional[float] = None
    yield_10y: Optional[float] = None
    yield_30y: Optional[float] = None

    spread_2s10s: Optional[float] = None
    spread_3m10y: Optional[float] = None

    vix:                 Optional[float] = None
    vix_percentile_1y:   Optional[float] = None
    dxy:                 Optional[float] = None
    hy_ig_proxy:         Optional[float] = None    # HYG/LQD price ratio gap
    hy_ig_proxy_z:       Optional[float] = None    # z-score vs 1y

    regime: MacroRegime = field(default_factory=lambda: MacroRegime(
        label="N/A", flag="unknown", score=0, reasons=[]
    ))
    note: str = ""


# ============================================================
# yfinance helpers
# ============================================================
def _last_close(symbol: str) -> Optional[float]:
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        df = yf.Ticker(symbol).history(period="5d")
    except Exception as e:
        logger.warning(f"yfinance history failed for {symbol}: {e}")
        return None
    if df is None or df.empty or "Close" not in df.columns:
        return None
    s = df["Close"].dropna()
    return float(s.iloc[-1]) if not s.empty else None


def _history(symbol: str, period: str = "1y") -> pd.Series:
    try:
        import yfinance as yf
    except ImportError:
        return pd.Series(dtype=float)
    try:
        df = yf.Ticker(symbol).history(period=period)
    except Exception:
        return pd.Series(dtype=float)
    if df is None or df.empty or "Close" not in df.columns:
        return pd.Series(dtype=float)
    return df["Close"].dropna()


# ============================================================
# Regime classifier
# ============================================================
def _classify_regime(snap: MacroSnapshot) -> MacroRegime:
    score = 0
    reasons: list[str] = []

    if snap.vix is not None and snap.vix_percentile_1y is not None:
        if snap.vix < 15 and snap.vix_percentile_1y < 30:
            score += 2
            reasons.append("Low equity vol (VIX bottom-quartile)")
        elif snap.vix > 25:
            score -= 2
            reasons.append(f"Elevated equity vol (VIX {snap.vix:.1f})")

    if snap.spread_2s10s is not None:
        if snap.spread_2s10s < -0.50:
            score -= 3
            reasons.append("2s10s deeply inverted")
        elif snap.spread_2s10s < 0:
            score -= 1
            reasons.append("2s10s inverted")

    if snap.spread_3m10y is not None:
        if snap.spread_3m10y < -0.50:
            score -= 3
            reasons.append("3m10y deeply inverted (Fed favourite signal)")
        elif snap.spread_3m10y < 0:
            score -= 1
            reasons.append("3m10y inverted")

    if snap.hy_ig_proxy_z is not None:
        if snap.hy_ig_proxy_z < -1.5:
            score -= 2
            reasons.append("HY/IG proxy stretched wider — risk-off")
        elif snap.hy_ig_proxy_z > 1.0:
            score += 1
            reasons.append("HY/IG proxy tight — risk-on")

    if score >= 2:
        label, flag = "RISK-ON", "green"
    elif score >= 0:
        label, flag = "NEUTRAL", "yellow"
    elif score >= -3:
        label, flag = "CAUTIOUS", "yellow"
    else:
        label, flag = "RISK-OFF", "red"

    return MacroRegime(label=label, flag=flag, score=score, reasons=reasons)


# ============================================================
# Public API
# ============================================================
def get_macro_snapshot() -> MacroSnapshot:
    snap = MacroSnapshot(available=False, timestamp=pd.Timestamp.utcnow())

    # CBOE / Treasury yield proxies — yfinance returns these as percentage
    # (e.g. ^TNX = 4.32 means 4.32%).
    snap.yield_3m  = _last_close("^IRX")
    snap.yield_5y  = _last_close("^FVX")
    snap.yield_10y = _last_close("^TNX")
    snap.yield_30y = _last_close("^TYX")
    # 2Y not directly on yfinance — fall back to a linear interp between 3M and 5Y
    if snap.yield_3m is not None and snap.yield_5y is not None:
        # 2Y ≈ midpoint weighted closer to 5Y on a flat curve
        snap.yield_2y = snap.yield_3m + (snap.yield_5y - snap.yield_3m) * (21 / 60)

    if snap.yield_10y is not None:
        if snap.yield_2y is not None:
            snap.spread_2s10s = snap.yield_10y - snap.yield_2y
        if snap.yield_3m is not None:
            snap.spread_3m10y = snap.yield_10y - snap.yield_3m

    # Vol
    snap.vix = _last_close("^VIX")
    if snap.vix is not None:
        vix_hist = _history("^VIX", "1y")
        if not vix_hist.empty:
            snap.vix_percentile_1y = float((vix_hist <= snap.vix).mean() * 100)

    # USD index
    snap.dxy = _last_close("DX-Y.NYB")

    # HY/IG proxy: ratio of HY corporate ETF to IG corporate ETF.
    # When HYG underperforms LQD, ratio falls → spreads widening → risk-off.
    hyg_hist = _history("HYG", "1y")
    lqd_hist = _history("LQD", "1y")
    if not hyg_hist.empty and not lqd_hist.empty:
        idx = hyg_hist.index.intersection(lqd_hist.index)
        if not idx.empty:
            ratio = (hyg_hist.loc[idx] / lqd_hist.loc[idx]).dropna()
            if not ratio.empty:
                snap.hy_ig_proxy = float(ratio.iloc[-1])
                if ratio.std() > 0:
                    snap.hy_ig_proxy_z = float(
                        (ratio.iloc[-1] - ratio.mean()) / ratio.std()
                    )

    snap.available = any(v is not None for v in (
        snap.yield_10y, snap.vix, snap.dxy,
    ))

    if not snap.available:
        snap.note = ("yfinance returned no data for any macro symbol — "
                     "rate-limited or offline. Try again in a minute.")
    else:
        snap.note = ("Yields are CBOE-quoted percentage points. 2Y is "
                     "interpolated (no native yfinance symbol). For CPI / "
                     "PCE / Sahm rule wire FRED.")

    snap.regime = _classify_regime(snap)
    return snap
