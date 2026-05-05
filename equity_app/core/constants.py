"""
Financial constants and literal user-facing strings.

ALL business assumptions live here. Changing a number here MUST NOT require
touching analysis/valuation/portfolio code.
"""
from __future__ import annotations

# ============================================================
# LITERAL USER-FACING MESSAGES
# Section 3, rule #1 — must be returned verbatim, no accents, no extra text.
# ============================================================
TICKER_NOT_FOUND_MESSAGE: str = "perdone, no se agrego la accion"

# ============================================================
# WACC
# ============================================================
DEFAULT_WACC_PARAMS: dict[str, float] = {
    "risk_free_rate": 0.045,        # 10Y US Treasury
    "market_risk_premium": 0.055,   # Damodaran ERP USA
    "tax_rate": 0.25,               # Effective US corporate
    "cost_of_debt": 0.05,
    "weight_equity": 0.70,
    "weight_debt": 0.30,
    "beta": 1.0,
}

# Beta regression (analysis/wacc.py)
BETA_REGRESSION = {
    "lookback_years": 5,
    "frequency": "M",               # monthly returns
    "benchmark_ticker": "^GSPC",    # S&P 500
}

# ============================================================
# DCF
# ============================================================
DCF_DEFAULTS: dict[str, float | int] = {
    "stage1_years": 5,                       # high growth
    "stage2_years": 5,                       # fade period
    "terminal_growth": 0.025,                # ~LP US inflation
    "growth_cap_upper": 0.30,
    "growth_cap_lower": -0.05,
    "min_wacc_terminal_spread": 0.005,       # WACC - g >= 50bp
    "fade_curve": "linear",                  # linear | logistic
}

# ============================================================
# Monte Carlo
# ============================================================
MONTE_CARLO_DEFAULTS: dict = {
    "n_simulations": 10_000,
    "rev_growth_std_floor": 0.02,            # min std for revenue growth
    "wacc_std": 0.005,
    "terminal_growth_low": 0.015,
    "terminal_growth_high": 0.035,
    "ebitda_margin_band": 0.02,              # ±2pp around historical
    "percentiles": (5, 25, 50, 75, 95),
}

# ============================================================
# Earnings quality
# ============================================================
BENEISH_THRESHOLD: float = -1.78             # > threshold => potential manipulator
PIOTROSKI_MAX: int = 9
PIOTROSKI_STRONG: int = 7                    # >= 7 strong
PIOTROSKI_WEAK: int = 3                      # <= 3 weak
SLOAN_RED_FLAG: float = 0.10                 # |accruals| / total assets > 10%

# ============================================================
# Balance sheet quality
# ============================================================
BS_QUALITY_THRESHOLDS: dict[str, float] = {
    "goodwill_red_flag": 0.40,
    "goodwill_yellow_flag": 0.20,
    "intangibles_red_flag": 0.50,
    "customer_concentration_red": 0.30,
}

# ============================================================
# Scoring (sector-normalized)
# ============================================================
SCORING_WEIGHTS: dict[str, float] = {
    "growth": 0.25,
    "profitability": 0.25,
    "solvency": 0.15,
    "earnings_quality": 0.15,
    "valuation": 0.20,
}

RATING_THRESHOLDS: dict[str, float] = {
    "strong_buy_upside": 0.30,
    "strong_buy_score": 70,
    "buy_upside": 0.10,
    "buy_score": 55,
    "hold_lower_upside": -0.15,
    "sell_upside": -0.15,
    "strong_sell_upside": -0.30,
    # Coefficient of variation across the 5 valuations above this => low confidence
    "low_confidence_dispersion": 0.30,
}

# ============================================================
# GICS sectors (11)
# ============================================================
GICS_SECTORS: tuple[str, ...] = (
    "Technology",
    "Healthcare",
    "Financial Services",
    "Consumer Cyclical",
    "Consumer Defensive",
    "Industrials",
    "Energy",
    "Utilities",
    "Basic Materials",
    "Real Estate",
    "Communication Services",
)

# Sector-specific weights for the valuation aggregator
SECTOR_VALUATION_WEIGHTS: dict[str, dict[str, float]] = {
    "tech_growth":   {"dcf": 0.55, "comps": 0.25, "monte_carlo": 0.20, "ddm": 0.00, "ri": 0.00},
    "financials":    {"dcf": 0.10, "comps": 0.30, "monte_carlo": 0.10, "ddm": 0.20, "ri": 0.30},
    "mature_div":    {"dcf": 0.30, "comps": 0.30, "monte_carlo": 0.00, "ddm": 0.40, "ri": 0.00},
    "default":       {"dcf": 0.40, "comps": 0.30, "monte_carlo": 0.20, "ddm": 0.05, "ri": 0.05},
}

# ============================================================
# Portfolio
# ============================================================
PORTFOLIO_DEFAULTS: dict[str, float | int] = {
    "trading_days": 252,
    "risk_free_rate": 0.045,
    "max_position_size": 0.30,
    "min_position_size": 0.01,
    "default_sector_cap": 0.40,
    "var_confidence": 0.95,
    "backtest_train_pct": 0.70,
    "rolling_window_months": 36,
}

# ============================================================
# Cache TTLs (seconds)
# ============================================================
CACHE_TTL: dict[str, int] = {
    "quote": 5,
    "fundamentals": 24 * 3600,
    "financials": 24 * 3600,
    "news": 3600,
    "insider": 6 * 3600,
    "screener": 1800,
    "damodaran": 7 * 24 * 3600,
    "beta": 7 * 24 * 3600,
    "fred": 6 * 3600,
    "prices_eod": 12 * 3600,
}

# ============================================================
# Comparables filtering
# ============================================================
COMPARABLES_FILTERING: dict = {
    "method": "iqr",                         # iqr | winsorize
    "iqr_multiplier": 1.5,
    "winsorize_lower": 0.05,
    "winsorize_upper": 0.95,
    "min_peers_after_filter": 3,
}

# ============================================================
# Real-time refresh
# ============================================================
REFRESH_DEFAULTS: dict[str, int] = {
    "quote_refresh_seconds": 5,
    "min_refresh_seconds": 1,
    "max_refresh_seconds": 60,
}
