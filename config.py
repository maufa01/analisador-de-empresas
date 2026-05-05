"""
Configuración global. Todos los supuestos están acá para que sean explícitos
y auditables. Cambiarlos NO requiere tocar la lógica.
"""

# WACC defaults — basados en mercado USA (Damodaran 2024)
DEFAULT_WACC_PARAMS = {
    "risk_free_rate": 0.045,       # 10Y Treasury yield aprox.
    "market_risk_premium": 0.055,  # Equity Risk Premium histórico USA
    "tax_rate": 0.25,              # Tax rate corporativo blended
    "cost_of_debt": 0.05,
    "weight_equity": 0.70,
    "weight_debt": 0.30,
    "beta": 1.0,                   # Override con info.get("beta") si está
}

# Proyección DCF
DCF_DEFAULTS = {
    "projection_years": 5,
    "terminal_growth": 0.025,  # ~inflación LP USA
    # Cap superior/inferior al growth implícito para evitar proyecciones
    # absurdas si la empresa creció 80% YoY un año (e.g. NVDA 2023).
    "growth_cap_upper": 0.20,
    "growth_cap_lower": -0.05,
}

# Pesos del scoring (suman 1.0)
SCORING_WEIGHTS = {
    "growth": 0.25,
    "profitability": 0.30,
    "solvency": 0.20,
    "valuation": 0.25,
}

# Umbrales del rating final (en upside vs precio actual)
RATING_THRESHOLDS = {
    "strong_buy": 0.25,   # >= +25%
    "buy": 0.10,          # >= +10%
    "hold_lower": -0.10,  # >= -10% sino SELL
}

# Markowitz
PORTFOLIO_DEFAULTS = {
    "trading_days": 252,
    "risk_free_rate": 0.045,
}
