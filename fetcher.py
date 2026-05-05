"""
Capa de acceso a datos. Encapsulamos yfinance detrás de una clase
`CompanyData` para poder cambiar el provider (Alpha Vantage, FMP, etc.)
sin tocar la lógica de análisis.

Notas sobre yfinance:
- `t.income_stmt`, `t.balance_sheet`, `t.cashflow` devuelven DataFrames
  con cuentas como filas y fechas como columnas (más reciente a la izq).
  Las normalizamos a índice temporal ascendente.
- Los nombres de cuentas cambian entre versiones. ratios.py resuelve
  por aliases.
- `t.info` puede tirar excepciones por rate limit. Lo manejamos.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class CompanyData:
    ticker: str
    info: dict = field(default_factory=dict)
    income_stmt: pd.DataFrame = field(default_factory=pd.DataFrame)
    balance_sheet: pd.DataFrame = field(default_factory=pd.DataFrame)
    cash_flow: pd.DataFrame = field(default_factory=pd.DataFrame)
    prices: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def current_price(self) -> Optional[float]:
        if not self.prices.empty:
            return float(self.prices["Close"].iloc[-1])
        return self.info.get("currentPrice") or self.info.get("regularMarketPrice")

    @property
    def shares_outstanding(self) -> Optional[float]:
        s = self.info.get("sharesOutstanding")
        return float(s) if s else None

    @property
    def market_cap(self) -> Optional[float]:
        return self.info.get("marketCap")

    @property
    def beta(self) -> Optional[float]:
        b = self.info.get("beta")
        return float(b) if b else None


def fetch_data(ticker: str, years: int = 5) -> CompanyData:
    """
    Obtiene financials + precios + info de una compañía.
    
    Args:
        ticker: símbolo (e.g. "AAPL")
        years: ventana de precios históricos (yfinance limita financials a ~4 años free)
    
    Raises:
        ValueError si el ticker no existe o no devolvió datos mínimos.
    """
    t = yf.Ticker(ticker)
    
    # info puede fallar por rate limit; capturamos
    try:
        info = t.info or {}
    except Exception as e:
        logger.warning("info() falló para %s: %s", ticker, e)
        info = {}

    # No usar `or` directo porque DataFrames empty levantan truth-value ambiguo
    income_raw = getattr(t, "income_stmt", None)
    if income_raw is None or (hasattr(income_raw, "empty") and income_raw.empty):
        income_raw = t.financials
    income = _normalize(income_raw)
    balance = _normalize(t.balance_sheet)
    cash = _normalize(t.cashflow)
    
    try:
        prices = t.history(period=f"{years}y", auto_adjust=True)
    except Exception as e:
        logger.warning("history() falló para %s: %s", ticker, e)
        prices = pd.DataFrame()
    
    if income.empty and balance.empty and prices.empty:
        raise ValueError(f"No se obtuvieron datos para {ticker}. ¿Ticker válido?")
    
    return CompanyData(
        ticker=ticker.upper(),
        info=info,
        income_stmt=income,
        balance_sheet=balance,
        cash_flow=cash,
        prices=prices,
    )


def _normalize(df: pd.DataFrame | None) -> pd.DataFrame:
    """Transpone y ordena ascendentemente por fecha."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.T.copy()
    try:
        out.index = pd.to_datetime(out.index)
    except Exception:
        pass
    return out.sort_index()


def fetch_peers(tickers: list[str], years: int = 5) -> dict[str, CompanyData]:
    """Bulk fetch para análisis de comparables. No paraleliza para evitar rate-limit."""
    out = {}
    for tk in tickers:
        try:
            out[tk] = fetch_data(tk, years)
        except Exception as e:
            logger.warning("Skipping peer %s: %s", tk, e)
    return out


def fetch_price_panel(tickers: list[str], years: int = 5) -> pd.DataFrame:
    """
    Panel de precios cierre ajustado para Markowitz.
    Devuelve DataFrame con un ticker por columna.
    """
    if len(tickers) == 1:
        df = yf.download(tickers[0], period=f"{years}y", auto_adjust=True, progress=False)
        return df[["Close"]].rename(columns={"Close": tickers[0]})
    
    data = yf.download(tickers, period=f"{years}y", auto_adjust=True, progress=False)
    if isinstance(data.columns, pd.MultiIndex):
        return data["Close"].dropna(how="all")
    return data
