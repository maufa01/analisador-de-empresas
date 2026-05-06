"""
SEC EDGAR provider — official US-listed company filings.

What this delivers (no API key needed; SEC requires a User-Agent
header identifying you):
    - CIK mapping (ticker → 10-digit Central Index Key)
    - Company Facts (the XBRL-tagged firehose of every reported
      financial concept, from 1993+ for many filers)
    - Annual / quarterly financials extracted from Company Facts
    - Filings index (10-K, 10-Q, 8-K, Form 4, 13F-HR, …)
    - Form 4 insider-transaction XML parser
    - 13F-HR institutional-holdings XML parser

All HTTP traffic is rate-limited to ~9 req/s (SEC's hard limit is 10);
429s back off and retry. Empty / failed responses degrade silently.

CIK mapping is cached locally (one tiny JSON file, refreshed weekly)
under ``~/.equity_app_cache/`` — no repo writes.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import json
import logging
import time

import pandas as pd

from core.config import read_secret

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================
SEC_BASE_URL          = "https://data.sec.gov"
SEC_TICKERS_URL       = "https://www.sec.gov/files/company_tickers.json"
SEC_RATE_LIMIT_DELAY  = 0.11      # 9 req/s — SEC hard cap is 10

_CACHE_DIR = Path.home() / ".equity_app_cache"
_CACHE_DIR.mkdir(exist_ok=True)
_CIK_CACHE_PATH = _CACHE_DIR / "sec_cik_mapping.json"
_CIK_CACHE_TTL_DAYS = 7

_last_request_at = 0.0


# ============================================================
# HTTP wrapper — single source for rate-limit + headers
# ============================================================
def _user_agent() -> str:
    ua = read_secret("SEC_USER_AGENT", "Equity App noreply@example.com")
    if "@" not in ua:
        ua = f"{ua} noreply@example.com"
    return ua


def _rate_limit() -> None:
    global _last_request_at
    elapsed = time.time() - _last_request_at
    if elapsed < SEC_RATE_LIMIT_DELAY:
        time.sleep(SEC_RATE_LIMIT_DELAY - elapsed)
    _last_request_at = time.time()


def _sec_get(url: str, *, max_retries: int = 3, timeout: int = 30) -> Any:
    """Returns parsed JSON dict, raw text, or {} on any failure."""
    try:
        import requests  # type: ignore
    except ImportError:
        return {}

    headers = {
        "User-Agent":      _user_agent(),
        "Accept-Encoding": "gzip, deflate",
    }

    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        _rate_limit()
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
        except Exception as e:
            last_exc = e
            time.sleep(2 ** attempt)
            continue

        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                return r.text
        if r.status_code == 404:
            return {}
        if r.status_code == 429:
            wait = (attempt + 1) * 5
            logger.warning(f"SEC 429 — backing off {wait}s")
            time.sleep(wait)
            continue
        if r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        return {}

    if last_exc:
        logger.warning(f"SEC request to {url} failed after retries: {last_exc}")
    return {}


def _sec_get_text(url: str, **kw) -> str:
    out = _sec_get(url, **kw)
    if isinstance(out, str):
        return out
    return ""


# ============================================================
# CIK mapping
# ============================================================
def _load_cik_cache() -> Optional[dict]:
    if not _CIK_CACHE_PATH.exists():
        return None
    try:
        age_days = (time.time() - _CIK_CACHE_PATH.stat().st_mtime) / 86400.0
    except OSError:
        return None
    if age_days > _CIK_CACHE_TTL_DAYS:
        return None
    try:
        return json.loads(_CIK_CACHE_PATH.read_text())
    except Exception:
        return None


def get_ticker_to_cik_mapping(force_refresh: bool = False) -> dict:
    """``{TICKER: {"cik": "0001234567", "name": "Apple Inc."}}`` — cached 7d."""
    if not force_refresh:
        cached = _load_cik_cache()
        if cached:
            return cached

    raw = _sec_get(SEC_TICKERS_URL)
    if not raw or not isinstance(raw, dict):
        if _CIK_CACHE_PATH.exists():
            try:
                return json.loads(_CIK_CACHE_PATH.read_text())
            except Exception:
                return {}
        return {}

    mapping = {}
    for item in raw.values():
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker", "")).upper().strip()
        cik = str(item.get("cik_str", "")).strip()
        if not ticker or not cik:
            continue
        mapping[ticker] = {"cik": cik.zfill(10), "name": item.get("title", ticker)}

    try:
        _CIK_CACHE_PATH.write_text(json.dumps(mapping))
    except OSError:
        pass
    return mapping


def get_cik_for_ticker(ticker: str) -> Optional[str]:
    if not ticker:
        return None
    mapping = get_ticker_to_cik_mapping()
    entry = mapping.get(ticker.upper())
    return entry["cik"] if entry else None


def get_company_name_from_cik(ticker: str) -> Optional[str]:
    mapping = get_ticker_to_cik_mapping()
    entry = mapping.get(ticker.upper())
    return entry["name"] if entry else None


# ============================================================
# Company Facts
# ============================================================
def get_company_facts(ticker: str) -> dict:
    cik = get_cik_for_ticker(ticker)
    if not cik:
        return {}
    url = f"{SEC_BASE_URL}/api/xbrl/companyfacts/CIK{cik}.json"
    out = _sec_get(url)
    return out if isinstance(out, dict) else {}


def get_company_concept(ticker: str, concept: str,
                        taxonomy: str = "us-gaap") -> dict:
    cik = get_cik_for_ticker(ticker)
    if not cik:
        return {}
    url = f"{SEC_BASE_URL}/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{concept}.json"
    out = _sec_get(url)
    return out if isinstance(out, dict) else {}


# ============================================================
# GAAP concept aliases — first match wins
# ============================================================
_GAAP_ALIASES: dict[str, list[str]] = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet", "SalesRevenueGoodsNet", "SalesRevenueServicesNet",
    ],
    "cost_of_revenue":  ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"],
    "gross_profit":     ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income":       ["NetIncomeLoss", "ProfitLoss",
                         "NetIncomeLossAvailableToCommonStockholdersBasic"],
    "eps_basic":        ["EarningsPerShareBasic"],
    "eps_diluted":      ["EarningsPerShareDiluted"],
    "shares_diluted":   ["WeightedAverageNumberOfDilutedSharesOutstanding"],
    "shares_basic":     ["WeightedAverageNumberOfSharesOutstandingBasic"],
    "shares_outstanding": ["CommonStockSharesOutstanding"],
    "tax_expense":      ["IncomeTaxExpenseBenefit"],
    "interest_expense": ["InterestExpense", "InterestExpenseDebt"],

    "total_assets":          ["Assets"],
    "current_assets":        ["AssetsCurrent"],
    "cash":                  ["CashAndCashEquivalentsAtCarryingValue", "Cash",
                              "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "short_term_investments": ["ShortTermInvestments", "MarketableSecuritiesCurrent"],
    "receivables":           ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent"],
    "inventory":             ["InventoryNet"],
    "ppe_net":               ["PropertyPlantAndEquipmentNet"],
    "goodwill":              ["Goodwill"],
    "intangibles":           ["IntangibleAssetsNetExcludingGoodwill",
                              "FiniteLivedIntangibleAssetsNet"],
    "total_liabilities":     ["Liabilities"],
    "current_liabilities":   ["LiabilitiesCurrent"],
    "accounts_payable":      ["AccountsPayableCurrent"],
    "long_term_debt":        ["LongTermDebt", "LongTermDebtNoncurrent"],
    "total_debt":            ["DebtCurrent", "DebtLongtermAndShorttermCombinedAmount"],
    "stockholders_equity":   ["StockholdersEquity",
                              "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],

    "operating_cash_flow":   ["NetCashProvidedByUsedInOperatingActivities"],
    "investing_cash_flow":   ["NetCashProvidedByUsedInInvestingActivities"],
    "financing_cash_flow":   ["NetCashProvidedByUsedInFinancingActivities"],
    "capex":                 ["PaymentsToAcquirePropertyPlantAndEquipment",
                              "PaymentsForCapitalImprovements"],
    "depreciation":          ["DepreciationDepletionAndAmortization", "Depreciation",
                              "DepreciationAndAmortization"],
    "dividends_paid":        ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"],
    "stock_repurchased":     ["PaymentsForRepurchaseOfCommonStock",
                              "PaymentsForRepurchaseOfEquity"],
    "stock_issued":          ["ProceedsFromIssuanceOfCommonStock",
                              "StockIssuedDuringPeriodValueNewIssues"],
}


def _facts_units(facts: dict, metric_key: str) -> Optional[list]:
    if "facts" not in facts or "us-gaap" not in facts.get("facts", {}):
        return None
    gaap = facts["facts"]["us-gaap"]
    for alias in _GAAP_ALIASES.get(metric_key, [metric_key]):
        if alias in gaap:
            units = gaap[alias].get("units", {})
            for unit_key in ("USD", "shares", "USD/shares"):
                if unit_key in units:
                    return units[unit_key]
            if units:
                return next(iter(units.values()))
    return None


# ============================================================
# Financials extraction
# ============================================================
_INCOME_METRICS = (
    "revenue", "cost_of_revenue", "gross_profit", "operating_income",
    "net_income", "eps_basic", "eps_diluted", "shares_diluted",
    "shares_basic", "tax_expense", "interest_expense",
)
_BALANCE_METRICS = (
    "total_assets", "current_assets", "cash", "short_term_investments",
    "receivables", "inventory", "ppe_net", "goodwill", "intangibles",
    "total_liabilities", "current_liabilities", "accounts_payable",
    "long_term_debt", "total_debt", "stockholders_equity",
    "shares_outstanding",
)
_CASHFLOW_METRICS = (
    "operating_cash_flow", "investing_cash_flow", "financing_cash_flow",
    "capex", "depreciation", "dividends_paid", "stock_repurchased",
    "stock_issued",
)


def _build_period_df(facts: dict, metrics: tuple[str, ...],
                     *, freq: str) -> pd.DataFrame:
    forms = ("10-K",) if freq == "annual" else ("10-Q", "10-K")
    fps = ("FY",)     if freq == "annual" else ("Q1", "Q2", "Q3", "FY")

    rows: dict[str, dict] = {}
    for metric in metrics:
        units = _facts_units(facts, metric)
        if not units:
            continue
        for entry in units:
            if entry.get("form") not in forms:
                continue
            if entry.get("fp") not in fps:
                continue
            end = entry.get("end")
            val = entry.get("val")
            if not end or val is None:
                continue
            row = rows.setdefault(end, {"period": entry.get("fp"),
                                        "form":   entry.get("form")})
            # If two filings touched the same period-end, prefer the latest
            if (metric not in row
                    or entry.get("filed", "") > row.get(f"{metric}_filed", "")):
                row[metric] = val
                row[f"{metric}_filed"] = entry.get("filed", "")

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame.from_dict(rows, orient="index")
    df = df.drop(columns=[c for c in df.columns if c.endswith("_filed")],
                 errors="ignore")
    df.index = pd.to_datetime(df.index)
    df.index.name = "period_end"
    return df.sort_index(ascending=True)


def extract_financials(ticker: str, *, freq: str = "annual") -> dict[str, pd.DataFrame]:
    """Returns ``{"income": DF, "balance": DF, "cashflow": DF}``."""
    facts = get_company_facts(ticker)
    if not facts or "facts" not in facts:
        return {"income": pd.DataFrame(), "balance": pd.DataFrame(),
                "cashflow": pd.DataFrame()}
    return {
        "income":   _build_period_df(facts, _INCOME_METRICS,   freq=freq),
        "balance":  _build_period_df(facts, _BALANCE_METRICS,  freq=freq),
        "cashflow": _build_period_df(facts, _CASHFLOW_METRICS, freq=freq),
    }


# ============================================================
# Filings index
# ============================================================
def get_filings_list(ticker: str, *,
                     form_types: Optional[list[str]] = None) -> pd.DataFrame:
    cik = get_cik_for_ticker(ticker)
    if not cik:
        return pd.DataFrame()
    url = f"{SEC_BASE_URL}/submissions/CIK{cik}.json"
    data = _sec_get(url)
    if not isinstance(data, dict) or not data:
        return pd.DataFrame()

    recent = data.get("filings", {}).get("recent", {})
    if not recent:
        return pd.DataFrame()

    df = pd.DataFrame({
        "form":             recent.get("form", []),
        "filing_date":      recent.get("filingDate", []),
        "report_date":      recent.get("reportDate", []),
        "accession_number": recent.get("accessionNumber", []),
        "primary_document": recent.get("primaryDocument", []),
    })
    if df.empty:
        return df
    df["filing_date"] = pd.to_datetime(df["filing_date"], errors="coerce")
    df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce")
    if form_types:
        df = df[df["form"].isin(form_types)]
    return df.sort_values("filing_date", ascending=False).reset_index(drop=True)


def filing_url(ticker: str, accession_number: str,
               primary_document: str) -> Optional[str]:
    cik = get_cik_for_ticker(ticker)
    if not cik:
        return None
    accession_clean = accession_number.replace("-", "")
    return (f"https://www.sec.gov/Archives/edgar/data/"
            f"{int(cik)}/{accession_clean}/{primary_document}")


# ============================================================
# Form 4 (insider) parser
# ============================================================
@dataclass
class Form4Transaction:
    transaction_date:  Optional[str]
    security_title:    Optional[str]
    transaction_code:  Optional[str]
    shares:            Optional[float]
    price:             Optional[float]
    acquired_disposed: Optional[str]
    shares_after:      Optional[float]


@dataclass
class Form4Filing:
    issuer_name:    Optional[str]
    issuer_ticker:  Optional[str]
    owner_name:     Optional[str]
    relationships:  list[str]
    transactions:   list[Form4Transaction]


def _safe_float(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_form4_xml(xml_text: str) -> Optional[Form4Filing]:
    if not xml_text:
        return None
    try:
        import xml.etree.ElementTree as ET
        payload = xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text
        root = ET.fromstring(payload)
    except Exception as e:
        logger.debug(f"Form 4 XML parse failed: {e}")
        return None

    rels: list[str] = []
    rel = root.find(".//reportingOwnerRelationship")
    if rel is not None:
        if (rel.findtext("isDirector") or "").strip() == "1":
            rels.append("Director")
        if (rel.findtext("isOfficer") or "").strip() == "1":
            title = (rel.findtext("officerTitle") or "Officer").strip()
            rels.append(title)
        if (rel.findtext("isTenPercentOwner") or "").strip() == "1":
            rels.append("10% Owner")

    txs: list[Form4Transaction] = []
    for tx in root.findall(".//nonDerivativeTransaction"):
        txs.append(Form4Transaction(
            transaction_date=tx.findtext(".//transactionDate/value"),
            security_title=tx.findtext(".//securityTitle/value"),
            transaction_code=tx.findtext(".//transactionCoded/transactionCode"),
            shares=_safe_float(tx.findtext(".//transactionAmounts/transactionShares/value")),
            price=_safe_float(tx.findtext(".//transactionAmounts/transactionPricePerShare/value")),
            acquired_disposed=tx.findtext(
                ".//transactionAmounts/transactionAcquiredDisposedCode/value"),
            shares_after=_safe_float(tx.findtext(
                ".//postTransactionAmounts/sharesOwnedFollowingTransaction/value")),
        ))

    return Form4Filing(
        issuer_name=root.findtext(".//issuerName"),
        issuer_ticker=root.findtext(".//issuerTradingSymbol"),
        owner_name=root.findtext(".//rptOwnerName"),
        relationships=rels,
        transactions=txs,
    )


FORM4_TRANSACTION_CODES = {
    "P": "Open-market purchase",
    "S": "Open-market sale",
    "A": "Grant / award",
    "D": "Sale to issuer",
    "F": "Tax withholding",
    "M": "Option exercise",
    "C": "Conversion of derivative",
    "G": "Bona fide gift",
    "J": "Other",
    "K": "Equity swap",
    "X": "Option exercise (in-the-money)",
}


# ============================================================
# 13F-HR parser
# ============================================================
@dataclass
class Holding13F:
    name_of_issuer:  Optional[str]
    cusip:           Optional[str]
    value_usd:       Optional[float]      # already converted from 1000s
    shares:          Optional[float]
    share_type:      Optional[str]


def parse_13f_xml(xml_text: str) -> list[Holding13F]:
    if not xml_text:
        return []
    try:
        import xml.etree.ElementTree as ET
        payload = xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text
        root = ET.fromstring(payload)
    except Exception as e:
        logger.debug(f"13F XML parse failed: {e}")
        return []

    # Strip namespaces — 13F XML is always namespaced
    for elem in root.iter():
        if isinstance(elem.tag, str) and "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]

    out: list[Holding13F] = []
    for it in root.findall(".//infoTable"):
        val = _safe_float(it.findtext("value"))
        out.append(Holding13F(
            name_of_issuer=it.findtext("nameOfIssuer"),
            cusip=it.findtext("cusip"),
            value_usd=(val * 1000) if val is not None else None,
            shares=_safe_float(it.findtext(".//sshPrnamt")),
            share_type=it.findtext(".//sshPrnamtType"),
        ))
    return out


# Famous-investor CIKs the UI can offer in a dropdown
FAMOUS_INVESTORS: dict[str, dict[str, str]] = {
    "BERKSHIRE":    {"name": "Berkshire Hathaway (Buffett)",       "cik": "0001067983"},
    "PABRAI":       {"name": "Pabrai Investment Funds",            "cik": "0001417659"},
    "SCION":        {"name": "Scion Asset Management (Burry)",     "cik": "0001649339"},
    "ARK":          {"name": "ARK Investment Management (Wood)",   "cik": "0001697748"},
    "BRIDGEWATER":  {"name": "Bridgewater Associates",             "cik": "0001350694"},
    "BAUPOST":      {"name": "Baupost Group (Klarman)",            "cik": "0001061768"},
    "TIGER_GLOBAL": {"name": "Tiger Global Management",            "cik": "0001167483"},
    "RENAISSANCE":  {"name": "Renaissance Technologies",           "cik": "0001037389"},
    "GREENLIGHT":   {"name": "Greenlight Capital (Einhorn)",       "cik": "0001079114"},
    "PERSHING":     {"name": "Pershing Square (Ackman)",           "cik": "0001336528"},
    "APPALOOSA":    {"name": "Appaloosa Management (Tepper)",      "cik": "0001656456"},
}


def get_13f_filings_for_cik(cik: str, *, limit: int = 12) -> pd.DataFrame:
    """List 13F-HR filings for a manager."""
    if not cik:
        return pd.DataFrame()
    cik10 = cik.zfill(10)
    url = f"{SEC_BASE_URL}/submissions/CIK{cik10}.json"
    data = _sec_get(url)
    if not isinstance(data, dict) or not data:
        return pd.DataFrame()
    recent = data.get("filings", {}).get("recent", {})
    df = pd.DataFrame({
        "form":             recent.get("form", []),
        "filing_date":      recent.get("filingDate", []),
        "report_date":      recent.get("reportDate", []),
        "accession_number": recent.get("accessionNumber", []),
        "primary_document": recent.get("primaryDocument", []),
    })
    if df.empty:
        return df
    df = df[df["form"] == "13F-HR"]
    df["filing_date"] = pd.to_datetime(df["filing_date"], errors="coerce")
    df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce")
    return df.sort_values("filing_date", ascending=False).head(limit).reset_index(drop=True)


def is_available() -> bool:
    """SEC EDGAR has no key — always available as long as we can reach it."""
    return True
