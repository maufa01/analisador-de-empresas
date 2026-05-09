"""
3-method VaR comparator with multi-day holding-period scaling.

Wraps :mod:`portfolio.var_calculator` for the historical and parametric
paths and adds a Student-t fitted Monte-Carlo for fat tails.

Sign convention: every ``var_pct`` and ``var_dollar`` returned here is
SIGNED (negative = a loss). The UI takes ``abs(...)`` when rendering.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from portfolio.var_calculator import value_at_risk, conditional_var


def _scale_returns(r: pd.Series, h: int) -> pd.Series:
    """Square-root-of-time scaling at the *return* level. Cheap and
    standard for short horizons; for very long h prefer compounding."""
    return r if h <= 1 else r * float(np.sqrt(h))


def historical_var_block(returns: pd.Series, *, confidence: float, h: int,
                         portfolio_value: float) -> dict:
    if returns is None or returns.empty:
        return {"error": "No returns"}
    scaled = _scale_returns(returns, h)
    var_pct = value_at_risk(scaled, confidence=confidence,
                            method="historical", signed=True)
    cvar_pct = conditional_var(scaled, confidence=confidence, signed=True)
    return {
        "method": "Historical",
        "var_pct": float(var_pct) * 100.0,
        "cvar_pct": float(cvar_pct) * 100.0,
        "var_dollar": float(var_pct) * portfolio_value,
        "cvar_dollar": float(cvar_pct) * portfolio_value,
        "n_observations": int(len(returns.dropna())),
    }


def parametric_var_block(returns: pd.Series, *, confidence: float, h: int,
                         portfolio_value: float) -> dict:
    if returns is None or returns.empty:
        return {"error": "No returns"}
    scaled = _scale_returns(returns, h)
    var_pct = value_at_risk(scaled, confidence=confidence,
                            method="parametric", signed=True)

    from scipy.stats import norm, jarque_bera
    r = returns.dropna()
    mu = float(r.mean()) * h
    sd = float(r.std(ddof=1)) * float(np.sqrt(h))
    z = float(norm.ppf(1.0 - confidence))
    cvar_pct = mu - sd * float(norm.pdf(z)) / (1.0 - confidence)

    is_normal = True
    try:
        if len(r) >= 8:
            _, p_norm = jarque_bera(r)
            is_normal = bool(p_norm > 0.05)
    except Exception:
        pass

    return {
        "method": "Parametric",
        "var_pct": float(var_pct) * 100.0,
        "cvar_pct": float(cvar_pct) * 100.0,
        "var_dollar": float(var_pct) * portfolio_value,
        "cvar_dollar": float(cvar_pct) * portfolio_value,
        "is_normal": is_normal,
        "warning": (None if is_normal else
                    "Returns deviate from normal — parametric likely "
                    "understates tail risk."),
    }


def monte_carlo_var_block(returns: pd.Series, *, confidence: float, h: int,
                          portfolio_value: float,
                          n_simulations: int = 10_000,
                          seed: int = 42) -> dict:
    if returns is None or returns.empty:
        return {"error": "No returns"}
    from scipy import stats
    r = returns.dropna().values
    if len(r) < 50:
        return {"error": "Need at least 50 observations"}

    df, loc, scale = stats.t.fit(r)
    rng = np.random.default_rng(seed)
    sims = stats.t.rvs(df, loc=loc, scale=scale,
                       size=(n_simulations, max(h, 1)),
                       random_state=rng).sum(axis=1)
    var_pct = float(np.quantile(sims, 1.0 - confidence))
    tail = sims[sims <= var_pct]
    cvar_pct = float(tail.mean()) if tail.size else float("nan")
    return {
        "method": "Monte Carlo",
        "var_pct": var_pct * 100.0,
        "cvar_pct": cvar_pct * 100.0,
        "var_dollar": var_pct * portfolio_value,
        "cvar_dollar": cvar_pct * portfolio_value,
        "fitted_distribution": f"Student-t (df={df:.2f})",
        "n_simulations": n_simulations,
        "simulated_returns": sims,
    }


def compare_methods(returns: pd.Series, *, portfolio_value: float,
                    confidence: float = 0.95, h: int = 1) -> dict:
    """Run all three VaR methods + a consensus banner."""
    hist = historical_var_block(returns, confidence=confidence, h=h,
                                 portfolio_value=portfolio_value)
    para = parametric_var_block(returns, confidence=confidence, h=h,
                                 portfolio_value=portfolio_value)
    mc = monte_carlo_var_block(returns, confidence=confidence, h=h,
                                portfolio_value=portfolio_value)

    estimates = [d["var_pct"] for d in (hist, para, mc) if "error" not in d]
    if len(estimates) >= 2:
        avg = float(np.mean(np.abs(estimates)))
        spread = float(max(estimates) - min(estimates))
        divergence = (abs(spread) / avg * 100.0) if avg > 0 else float("inf")
        if divergence < 10:
            consensus, color = "High consensus", "#10B981"
        elif divergence < 25:
            consensus, color = "Moderate consensus", "#C9A961"
        else:
            consensus, color = "Low consensus", "#B87333"
    else:
        consensus, color, divergence = "Insufficient data", "#6B7280", float("nan")

    return {
        "historical": hist,
        "parametric": para,
        "monte_carlo": mc,
        "consensus": consensus,
        "consensus_color": color,
        "divergence_pct": divergence,
    }
