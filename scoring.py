"""
Sistema de scoring 0-100 + rating final.

Filosofía:
- Cada componente normaliza a [0, 1] con min-max clipping
- Score total = suma ponderada con pesos en config.SCORING_WEIGHTS
- Rating combina upside + score (empresa cara pero buena = HOLD, no SELL)

Las heurísticas no son perfectas — son razonables y defendibles. Para
producción real se debería calibrar los rangos por sector.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from config import SCORING_WEIGHTS, RATING_THRESHOLDS


def _normalize(value, lo, hi):
    """Min-max clamp a [0, 1]. Si no es finito, devuelve 0.5."""
    if value is None or not np.isfinite(value):
        return 0.5
    return float(np.clip((value - lo) / (hi - lo), 0, 1))


def scoring_model(
    ratios: pd.DataFrame,
    current_price: float,
    intrinsic_price: float,
) -> dict:
    """
    Args:
        ratios: salida de calculate_ratios()
        current_price: precio actual
        intrinsic_price: valor intrínseco estimado (DCF, comps, o promedio)
    
    Returns:
        dict con score (0-100), components, upside (decimal), rating (str)
    """
    if ratios.empty:
        return {"score": 0, "components": {}, "upside": 0, "rating": "N/A"}
    
    last = ratios.iloc[-1]
    
    # === Growth: CAGR de revenue (rango: 0% -> 0, 25% -> 1) ===
    if "Revenue Growth %" in ratios.columns:
        rev_g = ratios["Revenue Growth %"].dropna().mean() / 100
    else:
        rev_g = 0
    s_growth = _normalize(rev_g, 0, 0.25)
    
    # === Profitability: ROE + Operating Margin ===
    roe = (last.get("ROE %", 0) or 0) / 100
    op_m = (last.get("Operating Margin %", 0) or 0) / 100
    s_prof = (_normalize(roe, 0, 0.25) + _normalize(op_m, 0, 0.25)) / 2
    
    # === Solvency: Debt/Equity bajo + Current Ratio sano ===
    de = last.get("Debt/Equity", 1.0)
    cr = last.get("Current Ratio", 1.0)
    de = de if pd.notna(de) else 1.0
    cr = cr if pd.notna(cr) else 1.0
    # D/E: 0 -> 1, 2 -> 0 (invertido)
    s_de = _normalize(2 - de, 0, 2)
    # CR: 1 -> 0, 2.5 -> 1
    s_cr = _normalize(cr, 1, 2.5)
    s_solv = (s_de + s_cr) / 2
    
    # === Valuation: upside ===
    if current_price and current_price > 0 and intrinsic_price:
        upside = (intrinsic_price - current_price) / current_price
    else:
        upside = 0
    s_val = _normalize(upside, -0.30, 0.50)
    
    components = {
        "growth": round(s_growth * 100, 1),
        "profitability": round(s_prof * 100, 1),
        "solvency": round(s_solv * 100, 1),
        "valuation": round(s_val * 100, 1),
    }
    
    score = (
        SCORING_WEIGHTS["growth"] * s_growth
        + SCORING_WEIGHTS["profitability"] * s_prof
        + SCORING_WEIGHTS["solvency"] * s_solv
        + SCORING_WEIGHTS["valuation"] * s_val
    ) * 100
    
    rating = _rating(upside, score)
    
    return {
        "score": round(score, 1),
        "components": components,
        "upside": float(upside),
        "rating": rating,
    }


def _rating(upside: float, score: float) -> str:
    """
    Combina upside con calidad fundamental.
    Si la empresa está barata pero es mala → HOLD (trampa de valor).
    Si está cara pero es excelente → HOLD, no SELL.
    """
    if upside >= RATING_THRESHOLDS["strong_buy"] and score >= 60:
        return "STRONG BUY"
    if upside >= RATING_THRESHOLDS["buy"]:
        return "BUY" if score >= 50 else "HOLD"
    if upside >= RATING_THRESHOLDS["hold_lower"]:
        return "HOLD"
    return "SELL"
