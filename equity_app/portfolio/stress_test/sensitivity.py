"""
Concentration risk + correlation diagnostics for stress reporting.

- ``concentration_metrics`` — HHI, top-N weights, effective N, sector
  breakdown, max-sector exposure
- ``beta_metrics`` — capital-weighted portfolio beta + qualitative
  profile (defensive / market-aligned / aggressive)
- ``false_diversification_pairs`` — asset pairs whose correlation
  exceeds a threshold (default 0.80) — diversification illusion
- ``crisis_correlation`` — average pairwise correlation in normal vs
  crisis days (avg-portfolio-return ≤ -2%); the spike between the two
  is a direct read on whether diversification holds in stress
"""
from __future__ import annotations
from typing import Mapping

import numpy as np
import pandas as pd


def concentration_metrics(holdings: Mapping[str, dict]) -> dict:
    """HHI + top-N + effective N + sector breakdown."""
    weights = pd.Series({t: float(info.get("weight", 0.0))
                         for t, info in holdings.items()})
    if weights.empty:
        return {"error": "No holdings"}
    total = float(weights.sum())
    if total > 0:
        weights = weights / total

    sum_sq = float((weights ** 2).sum())
    hhi = sum_sq * 10000.0
    if hhi < 1500:
        verdict = "Well diversified"
    elif hhi < 2500:
        verdict = "Moderately concentrated"
    else:
        verdict = "Highly concentrated"

    eff_n = (1.0 / sum_sq) if sum_sq > 0 else 0.0

    sector_w: dict[str, float] = {}
    for info in holdings.values():
        sec = info.get("sector") or "Unknown"
        sector_w[sec] = sector_w.get(sec, 0.0) + float(info.get("weight", 0.0))
    sec_series = pd.Series(sector_w).sort_values(ascending=False)
    if total > 0:
        sec_series = sec_series / total

    return {
        "hhi": hhi,
        "verdict": verdict,
        "top_1_pct": float(weights.max() * 100.0),
        "top_3_pct": float(weights.nlargest(min(3, len(weights))).sum() * 100.0),
        "top_5_pct": float(weights.nlargest(min(5, len(weights))).sum() * 100.0),
        "effective_n": float(eff_n),
        "n_positions": int(len(weights)),
        "max_sector": sec_series.index[0] if len(sec_series) else "—",
        "max_sector_pct": float(sec_series.iloc[0] * 100.0) if len(sec_series) else 0.0,
        "sector_breakdown": dict(sec_series),
    }


def beta_metrics(holdings: Mapping[str, dict]) -> dict:
    pairs = []
    for info in holdings.values():
        try:
            w = float(info.get("weight", 0.0))
            b = float(info.get("beta", 1.0) or 1.0)
            pairs.append((w, b))
        except (TypeError, ValueError):
            continue
    total_w = sum(w for w, _ in pairs)
    if total_w <= 0:
        return {"portfolio_beta": float("nan"), "profile": "—"}
    pb = sum(w * b for w, b in pairs) / total_w
    if pb < 0.85:
        profile = "Defensive"
    elif pb < 1.15:
        profile = "Market-aligned"
    else:
        profile = "Aggressive"
    return {"portfolio_beta": float(pb), "profile": profile}


def false_diversification_pairs(returns: pd.DataFrame,
                                threshold: float = 0.80) -> list[dict]:
    """Pairs with correlation > threshold — diversification illusions."""
    if returns is None or returns.shape[1] < 2:
        return []
    corr = returns.corr()
    pairs: list[dict] = []
    cols = corr.columns.tolist()
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            r = float(corr.iat[i, j])
            if np.isfinite(r) and r > threshold:
                pairs.append({"a": cols[i], "b": cols[j], "rho": r})
    return sorted(pairs, key=lambda d: -d["rho"])


def _avg_offdiag_corr(df: pd.DataFrame) -> float:
    if df is None or df.shape[1] < 2 or df.shape[0] < 2:
        return float("nan")
    c = df.corr().values
    n = c.shape[0]
    mask = ~np.eye(n, dtype=bool)
    return float(np.nanmean(c[mask]))


def crisis_correlation(returns: pd.DataFrame,
                       crisis_threshold: float = -0.02) -> dict:
    """Average pairwise correlation in normal vs crisis periods."""
    if returns is None or returns.empty:
        return {"error": "No data"}
    avg_daily = returns.mean(axis=1)
    normal = returns[avg_daily > crisis_threshold]
    crisis = returns[avg_daily <= crisis_threshold]
    if len(crisis) < 10:
        return {"error": "Insufficient crisis observations (need ≥10)"}

    nc = _avg_offdiag_corr(normal)
    cc = _avg_offdiag_corr(crisis)
    return {
        "normal_corr": nc,
        "crisis_corr": cc,
        "spike": (cc - nc) if (np.isfinite(cc) and np.isfinite(nc)) else float("nan"),
        "n_normal": int(len(normal)),
        "n_crisis": int(len(crisis)),
    }
