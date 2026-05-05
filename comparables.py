"""
Valuation por múltiplos comparables.

Para cada peer calculamos: P/E, EV/EBITDA, EV/Sales, P/B.
Usamos la MEDIANA del peer group (más robusta a outliers que el promedio)
y la aplicamos a las métricas del target para derivar precio implícito.

EV = Market Cap + Total Debt - Cash
Equity Value desde EV: equity = EV - Net Debt
Precio implícito = Equity Value / Shares Outstanding
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from ratios import _get


def _safe_ratio(num, den):
    if num is None or den is None or den == 0 or pd.isna(num) or pd.isna(den):
        return np.nan
    return num / den


def _last(series):
    """Último valor no-NaN de una serie, o None."""
    if series is None:
        return None
    s = series.dropna()
    return float(s.iloc[-1]) if not s.empty else None


def compute_multiples(company) -> dict:
    """Calcula los múltiplos actuales del company."""
    info = company.info
    income = company.income_stmt
    bs = company.balance_sheet

    market_cap = info.get("marketCap")
    price = company.current_price

    last_rev = _last(_get(income, "revenue"))
    last_ebitda = _last(_get(income, "ebitda"))
    if last_ebitda is None:
        # Reconstruir
        op = _last(_get(income, "operating_income"))
        da = _last(_get(company.cash_flow, "depreciation"))
        if op is not None and da is not None:
            last_ebitda = op + da
    last_ni = _last(_get(income, "net_income"))
    last_eq = _last(_get(bs, "total_equity"))
    last_debt = _last(_get(bs, "total_debt")) or 0.0
    last_cash = _last(_get(bs, "cash_eq")) or 0.0

    ev = (market_cap or 0) + last_debt - last_cash
    eps = info.get("trailingEps")

    return {
        "ticker": company.ticker,
        "Price": price,
        "MarketCap": market_cap,
        "EV": ev,
        "P/E": _safe_ratio(price, eps) if eps else np.nan,
        "EV/EBITDA": _safe_ratio(ev, last_ebitda),
        "EV/Sales": _safe_ratio(ev, last_rev),
        "P/B": _safe_ratio(market_cap, last_eq),
        "Revenue": last_rev,
        "EBITDA": last_ebitda,
        "NetIncome": last_ni,
        "Equity": last_eq,
        "EPS": eps,
        "Shares": company.shares_outstanding,
        "NetDebt": last_debt - last_cash,
    }


def comparables_model(target, peers: list) -> dict:
    """
    Aplica los múltiplos medianos del peer group al target.
    
    Returns dict con:
        target_multiples: dict con los múltiplos del target
        peers_table: DataFrame con los múltiplos de cada peer
        peer_stats: DataFrame con mean y median por múltiplo
        implied_prices: Series con precio implícito por cada múltiplo
        average_implied: precio implícito promedio (excluyendo NaN)
    """
    target_m = compute_multiples(target)
    peer_rows = [compute_multiples(p) for p in peers]
    peers_df = pd.DataFrame(peer_rows).set_index("ticker")

    multiples_cols = ["P/E", "EV/EBITDA", "EV/Sales", "P/B"]
    stats = peers_df[multiples_cols].agg(["mean", "median"])

    shares = target_m["Shares"] or 1
    net_debt = target_m["NetDebt"] or 0

    implied: dict[str, float] = {}
    median_pe = stats.loc["median", "P/E"]
    median_ev_ebitda = stats.loc["median", "EV/EBITDA"]
    median_ev_sales = stats.loc["median", "EV/Sales"]
    median_pb = stats.loc["median", "P/B"]

    if pd.notna(median_pe) and target_m["EPS"]:
        implied["P/E"] = float(target_m["EPS"] * median_pe)
    if pd.notna(median_ev_ebitda) and target_m["EBITDA"]:
        ev = target_m["EBITDA"] * median_ev_ebitda
        implied["EV/EBITDA"] = float((ev - net_debt) / shares)
    if pd.notna(median_ev_sales) and target_m["Revenue"]:
        ev = target_m["Revenue"] * median_ev_sales
        implied["EV/Sales"] = float((ev - net_debt) / shares)
    if pd.notna(median_pb) and target_m["Equity"]:
        implied["P/B"] = float(target_m["Equity"] * median_pb / shares)

    implied_series = pd.Series(implied, name="Implied Price").dropna()
    avg_implied = float(implied_series.mean()) if not implied_series.empty else None

    return {
        "target_multiples": target_m,
        "peers_table": peers_df,
        "peer_stats": stats,
        "implied_prices": implied_series,
        "average_implied": avg_implied,
    }
