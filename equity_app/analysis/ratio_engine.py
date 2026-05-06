"""
Ratio engine — 40+ financial ratios computed client-side from SEC EDGAR
statements. No network calls beyond the (cached) statement fetch in
``analysis.financial_statements``.

Why a single class:
    - One fetch, many derivations. Loading SEC Company Facts costs ~1
      HTTP round-trip; from that single payload we derive every ratio
      below.
    - Auditable. Each method's body is the formula. There's no second
      "true source" of, say, ROE — what you read here is what the UI
      shows.
    - Period-aware. Each method takes a ``period`` index (0 = most
      recent, 1 = prior year, …) so historical sweeps are cheap.

What this module does NOT own:
    - Display formatting (``ui.components.ratio_card`` handles that).
    - Industry benchmarks (``data.industry_benchmarks`` is the source).
"""
from __future__ import annotations
from typing import Optional

import logging
import pandas as pd

logger = logging.getLogger(__name__)


class RatioEngine:
    """
    Build with::

        engine = RatioEngine(ticker, market_cap=…, current_price=…)
        ratios = engine.compute_all()

    Each ratio method returns a ``float`` or ``None``. Margins / yields
    / returns are decimals (0.18 = 18%); ratios (D/E, current ratio,
    P/E…) are plain multipliers; days metrics are days.
    """

    def __init__(
        self,
        ticker: str,
        *,
        market_cap: Optional[float] = None,
        current_price: Optional[float] = None,
    ):
        self.ticker = ticker
        self.market_cap = market_cap
        self.current_price = current_price

        from analysis.financial_statements import get_standardised_statements

        annual = get_standardised_statements(ticker, freq="annual")
        quarterly = get_standardised_statements(ticker, freq="quarterly")

        # Wide DataFrames: rows = line items, columns = period_end (descending)
        self.income     = annual.income
        self.balance    = annual.balance
        self.cashflow   = annual.cashflow
        self.income_q   = quarterly.income
        self.balance_q  = quarterly.balance
        self.cashflow_q = quarterly.cashflow

        self.note = annual.note
        self.has_data = not self.income.empty

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------
    def _df(self, statement: str) -> pd.DataFrame:
        return getattr(self, statement, pd.DataFrame())

    def _get(self, statement: str, line: str,
             period: int = 0) -> Optional[float]:
        df = self._df(statement)
        if df.empty or line not in df.index or period >= len(df.columns):
            return None
        val = df.loc[line].iloc[period]
        try:
            return float(val) if pd.notna(val) else None
        except (TypeError, ValueError):
            return None

    def _avg(self, statement: str, line: str, *,
             period: int = 0, periods: int = 2) -> Optional[float]:
        """Average over the ``periods`` most recent periods starting at ``period``."""
        df = self._df(statement)
        if df.empty or line not in df.index:
            return None
        slice_ = df.loc[line].iloc[period:period + periods].dropna()
        if slice_.empty:
            return None
        try:
            return float(slice_.mean())
        except (TypeError, ValueError):
            return None

    def _ttm(self, statement: str, line: str) -> Optional[float]:
        """Sum the last 4 quarterly observations; None if fewer than 4."""
        df = self._df(f"{statement}_q")
        if df.empty or line not in df.index:
            return None
        s = df.loc[line].iloc[:4].dropna()
        if len(s) < 4:
            return None
        try:
            return float(s.sum())
        except (TypeError, ValueError):
            return None

    # ============================================================
    # Profitability
    # ============================================================
    def gross_margin(self, period: int = 0) -> Optional[float]:
        rev = self._get("income", "revenue", period)
        gp = self._get("income", "gross_profit", period)
        if rev and gp is not None and rev > 0:
            return gp / rev
        return None

    def operating_margin(self, period: int = 0) -> Optional[float]:
        rev = self._get("income", "revenue", period)
        op = self._get("income", "operating_income", period)
        if rev and op is not None and rev > 0:
            return op / rev
        return None

    def net_margin(self, period: int = 0) -> Optional[float]:
        rev = self._get("income", "revenue", period)
        ni = self._get("income", "net_income", period)
        if rev and ni is not None and rev > 0:
            return ni / rev
        return None

    def fcf_margin(self, period: int = 0) -> Optional[float]:
        rev = self._get("income", "revenue", period)
        fcf = self._get("cashflow", "free_cash_flow", period)
        if rev and fcf is not None and rev > 0:
            return fcf / rev
        return None

    def roe(self, period: int = 0) -> Optional[float]:
        ni = self._get("income", "net_income", period)
        eq = self._avg("balance", "stockholders_equity",
                       period=period, periods=2)
        if ni is not None and eq and eq > 0:
            return ni / eq
        return None

    def roa(self, period: int = 0) -> Optional[float]:
        ni = self._get("income", "net_income", period)
        ta = self._avg("balance", "total_assets",
                       period=period, periods=2)
        if ni is not None and ta and ta > 0:
            return ni / ta
        return None

    def roic(self, period: int = 0) -> Optional[float]:
        """NOPAT / Invested Capital. Uses effective tax when available,
        else 21% (US statutory) so ROIC isn't withheld for pure-tax-rate
        edge cases."""
        op = self._get("income", "operating_income", period)
        if op is None:
            return None
        tax_rate = self.effective_tax_rate(period)
        if tax_rate is None:
            tax_rate = 0.21
        nopat = op * (1.0 - tax_rate)

        debt = self._get("balance", "total_debt", period) or 0.0
        equity = self._get("balance", "stockholders_equity", period) or 0.0
        cash = self._get("balance", "cash", period) or 0.0
        invested = debt + equity - cash
        if invested > 0:
            return nopat / invested
        return None

    def roce(self, period: int = 0) -> Optional[float]:
        """EBIT / (Total Assets − Current Liabilities)."""
        op = self._get("income", "operating_income", period)
        ta = self._get("balance", "total_assets", period)
        cl = self._get("balance", "current_liabilities", period)
        if op is not None and ta and cl is not None:
            cap = ta - cl
            if cap > 0:
                return op / cap
        return None

    # ============================================================
    # Liquidity
    # ============================================================
    def current_ratio(self, period: int = 0) -> Optional[float]:
        ca = self._get("balance", "current_assets", period)
        cl = self._get("balance", "current_liabilities", period)
        if ca and cl and cl > 0:
            return ca / cl
        return None

    def quick_ratio(self, period: int = 0) -> Optional[float]:
        ca = self._get("balance", "current_assets", period) or 0.0
        inv = self._get("balance", "inventory", period) or 0.0
        cl = self._get("balance", "current_liabilities", period)
        if cl and cl > 0:
            return (ca - inv) / cl
        return None

    def cash_ratio(self, period: int = 0) -> Optional[float]:
        cash = self._get("balance", "cash", period) or 0.0
        sti = self._get("balance", "short_term_investments", period) or 0.0
        cl = self._get("balance", "current_liabilities", period)
        if cl and cl > 0:
            return (cash + sti) / cl
        return None

    def working_capital(self, period: int = 0) -> Optional[float]:
        ca = self._get("balance", "current_assets", period)
        cl = self._get("balance", "current_liabilities", period)
        if ca is not None and cl is not None:
            return ca - cl
        return None

    # ============================================================
    # Leverage
    # ============================================================
    def debt_to_equity(self, period: int = 0) -> Optional[float]:
        debt = self._get("balance", "total_debt", period) or 0.0
        eq = self._get("balance", "stockholders_equity", period)
        if eq and eq > 0:
            return debt / eq
        return None

    def debt_to_assets(self, period: int = 0) -> Optional[float]:
        debt = self._get("balance", "total_debt", period) or 0.0
        ta = self._get("balance", "total_assets", period)
        if ta and ta > 0:
            return debt / ta
        return None

    def debt_to_ebitda(self, period: int = 0) -> Optional[float]:
        debt = self._get("balance", "total_debt", period) or 0.0
        ebitda = self.ebitda(period)
        if ebitda and ebitda > 0:
            return debt / ebitda
        return None

    def interest_coverage(self, period: int = 0) -> Optional[float]:
        op = self._get("income", "operating_income", period)
        # Interest expense often reported as a negative number; absolute
        ie = self._get("income", "interest_expense", period)
        if op is not None and ie:
            ie_abs = abs(ie)
            if ie_abs > 0:
                return op / ie_abs
        return None

    def equity_ratio(self, period: int = 0) -> Optional[float]:
        eq = self._get("balance", "stockholders_equity", period)
        ta = self._get("balance", "total_assets", period)
        if eq and ta and ta > 0:
            return eq / ta
        return None

    # ============================================================
    # Efficiency
    # ============================================================
    def asset_turnover(self, period: int = 0) -> Optional[float]:
        rev = self._get("income", "revenue", period)
        ta = self._avg("balance", "total_assets",
                       period=period, periods=2)
        if rev and ta and ta > 0:
            return rev / ta
        return None

    def inventory_turnover(self, period: int = 0) -> Optional[float]:
        cogs = self._get("income", "cost_of_revenue", period)
        inv = self._avg("balance", "inventory",
                        period=period, periods=2)
        if cogs and inv and inv > 0:
            return cogs / inv
        return None

    def days_sales_outstanding(self, period: int = 0) -> Optional[float]:
        rev = self._get("income", "revenue", period)
        rec = self._avg("balance", "receivables",
                        period=period, periods=2)
        if rev and rec and rev > 0:
            return (rec / rev) * 365.0
        return None

    def days_inventory(self, period: int = 0) -> Optional[float]:
        turn = self.inventory_turnover(period)
        if turn and turn > 0:
            return 365.0 / turn
        return None

    def days_payables(self, period: int = 0) -> Optional[float]:
        cogs = self._get("income", "cost_of_revenue", period)
        ap = self._avg("balance", "accounts_payable",
                       period=period, periods=2)
        if cogs and ap and cogs > 0:
            return (ap / cogs) * 365.0
        return None

    def cash_conversion_cycle(self, period: int = 0) -> Optional[float]:
        dso = self.days_sales_outstanding(period)
        dio = self.days_inventory(period)
        dpo = self.days_payables(period)
        if dso is not None and dio is not None and dpo is not None:
            return dso + dio - dpo
        return None

    # ============================================================
    # Valuation (require live market data)
    # ============================================================
    def pe_ratio(self) -> Optional[float]:
        """Price / Trailing-12m EPS."""
        if not self.current_price:
            return None
        ttm_ni = self._ttm("income", "net_income")
        # Prefer diluted shares for the EPS divisor
        shares_ttm = self._ttm("income", "shares_diluted")
        if shares_ttm is None:
            shares_ttm = self._get("income", "shares_diluted", 0)
        if ttm_ni and shares_ttm and shares_ttm > 0:
            # ttm shares from quarterly data sums averages — divide by 4
            # to recover the avg outstanding count over the trailing year
            avg_shares = shares_ttm / 4 if self._ttm("income", "shares_diluted") else shares_ttm
            eps_ttm = ttm_ni / avg_shares
            if eps_ttm > 0:
                return self.current_price / eps_ttm
        return None

    def pb_ratio(self) -> Optional[float]:
        if not self.market_cap:
            return None
        eq = self._get("balance", "stockholders_equity", 0)
        if eq and eq > 0:
            return self.market_cap / eq
        return None

    def ps_ratio(self) -> Optional[float]:
        if not self.market_cap:
            return None
        ttm_rev = self._ttm("income", "revenue")
        if ttm_rev and ttm_rev > 0:
            return self.market_cap / ttm_rev
        return None

    def ev_to_ebitda(self) -> Optional[float]:
        ev = self.enterprise_value()
        ebitda = self.ebitda(0)
        if ev and ebitda and ebitda > 0:
            return ev / ebitda
        return None

    def ev_to_revenue(self) -> Optional[float]:
        ev = self.enterprise_value()
        ttm_rev = self._ttm("income", "revenue") or self._get("income", "revenue", 0)
        if ev and ttm_rev and ttm_rev > 0:
            return ev / ttm_rev
        return None

    def fcf_yield(self) -> Optional[float]:
        if not self.market_cap or self.market_cap <= 0:
            return None
        fcf = self._ttm("cashflow", "free_cash_flow") or self._get("cashflow", "free_cash_flow", 0)
        if fcf is not None:
            return fcf / self.market_cap
        return None

    def earnings_yield(self) -> Optional[float]:
        pe = self.pe_ratio()
        if pe and pe > 0:
            return 1.0 / pe
        return None

    # ============================================================
    # Growth (CAGR)
    # ============================================================
    def _cagr_from_index(self, statement: str, line: str,
                         years: int) -> Optional[float]:
        df = self._df(statement)
        if df.empty or line not in df.index or len(df.columns) < years + 1:
            return None
        recent = df.loc[line].iloc[0]
        old = df.loc[line].iloc[years]
        try:
            recent = float(recent)
            old = float(old)
        except (TypeError, ValueError):
            return None
        if old <= 0 or pd.isna(recent) or pd.isna(old):
            return None
        return (recent / old) ** (1.0 / years) - 1.0

    def revenue_cagr(self, years: int = 5) -> Optional[float]:
        return self._cagr_from_index("income", "revenue", years)

    def eps_cagr(self, years: int = 5) -> Optional[float]:
        # Prefer diluted EPS; fall back to basic
        v = self._cagr_from_index("income", "eps_diluted", years)
        if v is None:
            v = self._cagr_from_index("income", "eps_basic", years)
        return v

    def fcf_cagr(self, years: int = 5) -> Optional[float]:
        return self._cagr_from_index("cashflow", "free_cash_flow", years)

    def net_income_cagr(self, years: int = 5) -> Optional[float]:
        return self._cagr_from_index("income", "net_income", years)

    # ============================================================
    # Derived
    # ============================================================
    def ebitda(self, period: int = 0) -> Optional[float]:
        op = self._get("income", "operating_income", period)
        da = self._get("cashflow", "depreciation", period)
        if op is None and da is None:
            return None
        return (op or 0.0) + (da or 0.0)

    def enterprise_value(self) -> Optional[float]:
        if not self.market_cap:
            return None
        debt = self._get("balance", "total_debt", 0) or 0.0
        cash = self._get("balance", "cash", 0) or 0.0
        return self.market_cap + debt - cash

    def effective_tax_rate(self, period: int = 0) -> Optional[float]:
        tax = self._get("income", "tax_expense", period)
        op = self._get("income", "operating_income", period)
        ie = abs(self._get("income", "interest_expense", period) or 0.0)
        if tax is None or op is None:
            return None
        pretax = op - ie
        if pretax > 0:
            rate = tax / pretax
            # Sanity clamp — reported tax can produce nonsense if any line is wrong
            return float(max(-0.5, min(0.6, rate)))
        return None

    # ============================================================
    # DuPont
    # ============================================================
    def dupont_decomposition(self, period: int = 0) -> dict:
        nm = self.net_margin(period)
        at = self.asset_turnover(period)
        avg_assets = self._avg("balance", "total_assets", period=period, periods=2)
        avg_eq = self._avg("balance", "stockholders_equity", period=period, periods=2)
        em = (avg_assets / avg_eq) if avg_assets and avg_eq and avg_eq > 0 else None

        roe_calc: Optional[float] = None
        if nm is not None and at is not None and em is not None:
            roe_calc = nm * at * em

        return {
            "net_margin":         nm,
            "asset_turnover":     at,
            "equity_multiplier":  em,
            "roe_calculated":     roe_calc,
            "roe_reported":       self.roe(period),
        }

    # ============================================================
    # Aggregate exports
    # ============================================================
    _CATEGORIES: dict[str, list[str]] = {
        "Profitability":  ["gross_margin", "operating_margin", "net_margin",
                            "fcf_margin", "roe", "roa", "roic", "roce"],
        "Liquidity":      ["current_ratio", "quick_ratio", "cash_ratio",
                            "working_capital"],
        "Leverage":       ["debt_to_equity", "debt_to_assets", "debt_to_ebitda",
                            "interest_coverage", "equity_ratio"],
        "Efficiency":     ["asset_turnover", "inventory_turnover",
                            "days_sales_outstanding", "days_inventory",
                            "days_payables", "cash_conversion_cycle"],
        "Valuation":      ["pe_ratio", "pb_ratio", "ps_ratio", "ev_to_ebitda",
                            "ev_to_revenue", "fcf_yield", "earnings_yield"],
        "Growth":         ["revenue_cagr_5y", "revenue_cagr_10y",
                            "eps_cagr_5y", "fcf_cagr_5y", "net_income_cagr_5y"],
    }

    @classmethod
    def categories(cls) -> dict[str, list[str]]:
        return dict(cls._CATEGORIES)

    def compute_all(self) -> dict[str, Optional[float]]:
        """Snapshot of every ratio for the most recent period."""
        out: dict[str, Optional[float]] = {}
        # Profitability + leverage + liquidity + efficiency: period 0
        for ratio in (
            "gross_margin operating_margin net_margin fcf_margin "
            "roe roa roic roce "
            "current_ratio quick_ratio cash_ratio working_capital "
            "debt_to_equity debt_to_assets debt_to_ebitda interest_coverage equity_ratio "
            "asset_turnover inventory_turnover "
            "days_sales_outstanding days_inventory days_payables cash_conversion_cycle "
            "ebitda enterprise_value effective_tax_rate"
        ).split():
            method = getattr(self, ratio, None)
            if method is None:
                out[ratio] = None
                continue
            try:
                out[ratio] = method()
            except Exception as e:
                logger.debug(f"{ratio} failed: {e}")
                out[ratio] = None

        # Valuation (no period arg)
        for ratio in ("pe_ratio pb_ratio ps_ratio ev_to_ebitda ev_to_revenue "
                      "fcf_yield earnings_yield").split():
            try:
                out[ratio] = getattr(self, ratio)()
            except Exception:
                out[ratio] = None

        # Growth — CAGR with explicit window
        out["revenue_cagr_5y"]    = self.revenue_cagr(5)
        out["revenue_cagr_10y"]   = self.revenue_cagr(10)
        out["eps_cagr_5y"]        = self.eps_cagr(5)
        out["fcf_cagr_5y"]        = self.fcf_cagr(5)
        out["net_income_cagr_5y"] = self.net_income_cagr(5)

        # DuPont as a sub-dict
        out["dupont"] = self.dupont_decomposition()
        return out

    def compute_historical(
        self, ratios: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        """Period-by-period sweep of selected ratios. Index = period_end."""
        if ratios is None:
            ratios = ["roe", "roa", "roic", "gross_margin", "operating_margin",
                      "net_margin", "fcf_margin", "debt_to_equity",
                      "current_ratio", "asset_turnover"]
        if self.income.empty:
            return pd.DataFrame()
        n = len(self.income.columns)
        rows: dict[str, list] = {r: [] for r in ratios}
        for period in range(n):
            for ratio in ratios:
                method = getattr(self, ratio, None)
                if method is None:
                    rows[ratio].append(None)
                    continue
                try:
                    rows[ratio].append(method(period))
                except Exception:
                    rows[ratio].append(None)
        return pd.DataFrame(rows, index=self.income.columns)
