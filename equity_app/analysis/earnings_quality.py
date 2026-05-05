"""
Earnings-quality detection: Beneish M-Score, Piotroski F-Score, Sloan ratio.

All three operate on the same ratios input shape (FMP-style) and emit a
green/yellow/red flag with a one-line explanation. None of them is
predictive on its own — together they triangulate the signal.

References:
- Beneish (1999), "The Detection of Earnings Manipulation"
- Piotroski (2000), "Value Investing: The Use of Historical Financial
  Statement Information to Separate Winners from Losers"
- Sloan (1996), "Do Stock Prices Fully Reflect Information in
  Accruals and Cash Flows about Future Earnings?"
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from .ratios import _get
from core.constants import (
    BENEISH_THRESHOLD, PIOTROSKI_MAX, PIOTROSKI_STRONG, PIOTROSKI_WEAK,
    SLOAN_RED_FLAG,
)


# ============================================================
# Output dataclasses
# ============================================================
@dataclass
class QualityFlag:
    """A single signal with severity + explanation."""
    name: str
    score: float
    flag: str             # "green" | "yellow" | "red"
    explanation: str
    components: dict = field(default_factory=dict)


@dataclass
class EarningsQuality:
    beneish: Optional[QualityFlag] = None
    piotroski: Optional[QualityFlag] = None
    sloan: Optional[QualityFlag] = None

    @property
    def overall_flag(self) -> str:
        """Worst-of: any red ⇒ red, any yellow ⇒ yellow, else green."""
        flags = [f.flag for f in (self.beneish, self.piotroski, self.sloan) if f is not None]
        if not flags:
            return "unknown"
        if "red" in flags:
            return "red"
        if "yellow" in flags:
            return "yellow"
        return "green"


# ============================================================
# Beneish M-Score
# ============================================================
def beneish_m_score(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
) -> Optional[QualityFlag]:
    """
    Beneish (1999) 8-variable composite. Threshold: M > -1.78 ⇒ potential
    earnings manipulator.

    Variables (subscripts t = current year, t-1 = prior year):
      DSRI = (AR_t / Sales_t) / (AR_t-1 / Sales_t-1)
      GMI  = GM_t-1 / GM_t
      AQI  = (1 - (CA + PPE)/TA)_t / (1 - (CA + PPE)/TA)_t-1
      SGI  = Sales_t / Sales_t-1
      DEPI = (Dep / (Dep + PPE))_t-1 / (Dep / (Dep + PPE))_t
      SGAI = (SGA / Sales)_t / (SGA / Sales)_t-1
      LVGI = ((LTD + CL) / TA)_t / ((LTD + CL) / TA)_t-1
      TATA = (NI - CFO) / TA_t

    M = -4.84 + 0.92 DSRI + 0.528 GMI + 0.404 AQI + 0.892 SGI
        + 0.115 DEPI - 0.172 SGAI + 4.679 TATA - 0.327 LVGI
    """
    rev = _get(income, "revenue")
    gp = _get(income, "gross_profit")
    sga = _get(income, "sga")
    ni = _get(income, "net_income")
    ta = _get(balance, "total_assets")
    ca = _get(balance, "current_assets")
    cl = _get(balance, "current_liabilities")
    ar = _get(balance, "receivables")
    ppe = _get(balance, "ppe")
    ltd = _get(balance, "long_term_debt")
    dep = _get(cash, "depreciation_cf")
    cfo = _get(cash, "ocf")

    required = (rev, ar, ta, ca, ppe, dep, cfo, gp, ltd, cl)
    if any(s is None or len(s.dropna()) < 2 for s in required):
        return None

    def _last_two(series: pd.Series) -> tuple[float, float]:
        s = series.dropna()
        return float(s.iloc[-2]), float(s.iloc[-1])

    rev_p, rev_t = _last_two(rev)        # type: ignore[arg-type]
    ar_p, ar_t = _last_two(ar)           # type: ignore[arg-type]
    ta_p, ta_t = _last_two(ta)           # type: ignore[arg-type]
    ca_p, ca_t = _last_two(ca)           # type: ignore[arg-type]
    ppe_p, ppe_t = _last_two(ppe)        # type: ignore[arg-type]
    dep_p, dep_t = _last_two(dep)        # type: ignore[arg-type]
    gp_p, gp_t = _last_two(gp)           # type: ignore[arg-type]
    ltd_p, ltd_t = _last_two(ltd)        # type: ignore[arg-type]
    cl_p, cl_t = _last_two(cl)           # type: ignore[arg-type]

    # SGAI is optional — neutral 1.0 if SGA not reported
    if sga is not None and len(sga.dropna()) >= 2:
        sga_p, sga_t = _last_two(sga)    # type: ignore[arg-type]
    else:
        sga_p, sga_t = None, None

    if ni is None or ni.dropna().empty:
        return None
    ni_t = float(ni.dropna().iloc[-1])
    cfo_t = float(cfo.dropna().iloc[-1])

    try:
        dsri = (ar_t / rev_t) / (ar_p / rev_p)
        gmi = (gp_p / rev_p) / (gp_t / rev_t)
        aqi_t = 1 - (ca_t + ppe_t) / ta_t
        aqi_p = 1 - (ca_p + ppe_p) / ta_p
        aqi = aqi_t / aqi_p if aqi_p else float("nan")
        sgi = rev_t / rev_p
        depi_t = dep_t / (dep_t + ppe_t) if (dep_t + ppe_t) else float("nan")
        depi_p = dep_p / (dep_p + ppe_p) if (dep_p + ppe_p) else float("nan")
        depi = depi_p / depi_t if depi_t else float("nan")
        if sga_t is not None and sga_p is not None and rev_t and rev_p:
            sgai = (sga_t / rev_t) / (sga_p / rev_p)
        else:
            sgai = 1.0
        lvgi = ((ltd_t + cl_t) / ta_t) / ((ltd_p + cl_p) / ta_p)
        tata = (ni_t - cfo_t) / ta_t
    except Exception:
        return None

    if any(not np.isfinite(x) for x in (dsri, gmi, aqi, sgi, depi, sgai, lvgi, tata)):
        return None

    m = (
        -4.84
        + 0.92 * dsri
        + 0.528 * gmi
        + 0.404 * aqi
        + 0.892 * sgi
        + 0.115 * depi
        - 0.172 * sgai
        + 4.679 * tata
        - 0.327 * lvgi
    )

    if m > BENEISH_THRESHOLD:
        flag = "red"
        explanation = (
            f"M-Score {m:.2f} > {BENEISH_THRESHOLD}: "
            "potential earnings-manipulation signature."
        )
    elif m > BENEISH_THRESHOLD - 0.5:
        flag = "yellow"
        explanation = f"M-Score {m:.2f}: borderline; review accruals and revenue recognition."
    else:
        flag = "green"
        explanation = f"M-Score {m:.2f} < {BENEISH_THRESHOLD}: low manipulation risk."

    return QualityFlag(
        name="Beneish M-Score",
        score=float(m),
        flag=flag,
        explanation=explanation,
        components={
            "DSRI": float(dsri), "GMI": float(gmi), "AQI": float(aqi),
            "SGI": float(sgi), "DEPI": float(depi), "SGAI": float(sgai),
            "LVGI": float(lvgi), "TATA": float(tata),
        },
    )


# ============================================================
# Piotroski F-Score
# ============================================================
def piotroski_f_score(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
) -> Optional[QualityFlag]:
    """
    Piotroski (2000). 9 binary points across profitability, leverage and
    operating efficiency. Higher is better.
    """
    ni = _get(income, "net_income")
    rev = _get(income, "revenue")
    gp = _get(income, "gross_profit")
    ta = _get(balance, "total_assets")
    ca = _get(balance, "current_assets")
    cl = _get(balance, "current_liabilities")
    ltd = _get(balance, "long_term_debt")
    cfo = _get(cash, "ocf")
    shares = _get(income, "weighted_avg_shares")
    if shares is None:
        shares = _get(balance, "common_shares_outstanding")

    if any(s is None or len(s.dropna()) < 2 for s in (ni, rev, ta, cfo)):
        return None

    def _t_p(series: pd.Series) -> tuple[float, float]:
        s = series.dropna()
        return float(s.iloc[-1]), float(s.iloc[-2])

    ni_t, ni_p = _t_p(ni)        # type: ignore[arg-type]
    rev_t, rev_p = _t_p(rev)     # type: ignore[arg-type]
    ta_t, ta_p = _t_p(ta)        # type: ignore[arg-type]
    cfo_t, _cfo_p = _t_p(cfo)    # type: ignore[arg-type]

    points: dict[str, int] = {}

    points["ROA > 0"] = int(ni_t / ta_t > 0)
    points["CFO > 0"] = int(cfo_t > 0)
    points["dROA > 0"] = int((ni_t / ta_t) > (ni_p / ta_p))
    points["CFO > NI"] = int(cfo_t > ni_t)

    if ltd is not None and len(ltd.dropna()) >= 2:
        ltd_t, ltd_p = _t_p(ltd)        # type: ignore[arg-type]
        points["dLT Debt < 0"] = int(ltd_t < ltd_p)
    else:
        points["dLT Debt < 0"] = 0

    if ca is not None and cl is not None and len(ca.dropna()) >= 2 and len(cl.dropna()) >= 2:
        ca_t, ca_p = _t_p(ca)            # type: ignore[arg-type]
        cl_t, cl_p = _t_p(cl)            # type: ignore[arg-type]
        cr_t = ca_t / cl_t if cl_t else float("nan")
        cr_p = ca_p / cl_p if cl_p else float("nan")
        points["dCurrent Ratio > 0"] = int(np.isfinite(cr_t) and np.isfinite(cr_p) and cr_t > cr_p)
    else:
        points["dCurrent Ratio > 0"] = 0

    if shares is not None and len(shares.dropna()) >= 2:
        sh_t, sh_p = _t_p(shares)        # type: ignore[arg-type]
        points["No new shares"] = int(sh_t <= sh_p)
    else:
        points["No new shares"] = 0

    if gp is not None and len(gp.dropna()) >= 2:
        gp_t, gp_p = _t_p(gp)            # type: ignore[arg-type]
        points["dGross Margin > 0"] = int((gp_t / rev_t) > (gp_p / rev_p))
    else:
        points["dGross Margin > 0"] = 0

    points["dAsset Turnover > 0"] = int((rev_t / ta_t) > (rev_p / ta_p))

    score = sum(points.values())

    if score >= PIOTROSKI_STRONG:
        flag = "green"
        explanation = f"F-Score {score}/{PIOTROSKI_MAX}: strong fundamentals."
    elif score <= PIOTROSKI_WEAK:
        flag = "red"
        explanation = f"F-Score {score}/{PIOTROSKI_MAX}: weak fundamentals."
    else:
        flag = "yellow"
        explanation = f"F-Score {score}/{PIOTROSKI_MAX}: mixed signals."

    return QualityFlag(
        name="Piotroski F-Score",
        score=float(score),
        flag=flag,
        explanation=explanation,
        components={k: int(v) for k, v in points.items()},
    )


# ============================================================
# Sloan ratio
# ============================================================
def sloan_ratio(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
) -> Optional[QualityFlag]:
    """
    Sloan = (NI − CFO) / avg(Total Assets).

    |Sloan| > 0.10 ⇒ red flag — earnings driven by accruals rather than
    cash. Sustained high accruals predict future negative surprises.
    """
    ni = _get(income, "net_income")
    cfo = _get(cash, "ocf")
    ta = _get(balance, "total_assets")
    if ni is None or cfo is None or ta is None:
        return None
    if ni.dropna().empty or cfo.dropna().empty or ta.dropna().empty:
        return None

    ni_t = float(ni.dropna().iloc[-1])
    cfo_t = float(cfo.dropna().iloc[-1])
    ta_dropped = ta.dropna()
    avg_ta = (
        float((ta_dropped.iloc[-1] + ta_dropped.iloc[-2]) / 2)
        if len(ta_dropped) >= 2
        else float(ta_dropped.iloc[-1])
    )
    if avg_ta == 0 or not np.isfinite(avg_ta):
        return None

    sloan = (ni_t - cfo_t) / avg_ta

    if abs(sloan) > SLOAN_RED_FLAG:
        flag = "red"
        explanation = (
            f"Sloan {sloan:+.2%}: accruals exceed {SLOAN_RED_FLAG:.0%} of "
            "total assets — earnings driven by non-cash items."
        )
    elif abs(sloan) > SLOAN_RED_FLAG / 2:
        flag = "yellow"
        explanation = f"Sloan {sloan:+.2%}: moderate accruals; monitor."
    else:
        flag = "green"
        explanation = f"Sloan {sloan:+.2%}: clean — earnings tracking cash."

    return QualityFlag(
        name="Sloan Ratio",
        score=float(sloan),
        flag=flag,
        explanation=explanation,
        components={"NI": ni_t, "CFO": cfo_t, "avg_TA": avg_ta},
    )


# ============================================================
# Aggregator
# ============================================================
def assess_earnings_quality(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cash: pd.DataFrame,
) -> EarningsQuality:
    """Run all three checks; missing inputs leave the slot as None."""
    return EarningsQuality(
        beneish=beneish_m_score(income, balance, cash),
        piotroski=piotroski_f_score(income, balance, cash),
        sloan=sloan_ratio(income, balance, cash),
    )
