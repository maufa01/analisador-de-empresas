"""
Pretty labels for FMP / yfinance camelCase financial statement fields.

Plus per-statement "row order + subtotal markers" used by the financial
table renderer to draw hierarchy (Revenue → Gross Profit → Operating
Income → Net Income, etc.).

The HYBRID view (analyst-spreadsheet style) uses richer layouts with
``DerivedRow`` markers — rows computed inline from already-loaded
absolute rows (% YoY change, % margins, % of total).
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Literal, Optional, Union


# ============================================================
# Pretty labels — camelCase → human
# ============================================================
ACCOUNT_LABELS: dict[str, str] = {
    # ---- Income Statement ----
    "revenue":                                  "Revenue",
    "totalRevenue":                             "Revenue",
    "costOfRevenue":                            "Cost of Revenue",
    "grossProfit":                              "Gross Profit",
    "sellingGeneralAndAdministrativeExpenses":  "SG&A",
    "researchAndDevelopmentExpenses":           "R&D",
    "operatingExpenses":                        "Operating Expenses",
    "operatingIncome":                          "Operating Income",
    "ebit":                                     "EBIT",
    "ebitda":                                   "EBITDA",
    "interestExpense":                          "Interest Expense",
    "interestIncome":                           "Interest Income",
    "incomeBeforeTax":                          "Income Before Tax",
    "incomeTaxExpense":                         "Tax Expense",
    "netIncome":                                "Net Income",
    "eps":                                      "EPS",
    "epsdiluted":                               "EPS (Diluted)",
    "weightedAverageShsOut":                    "Weighted Avg Shares",
    "weightedAverageShsOutDil":                 "Weighted Avg Shares (Diluted)",
    "depreciationAndAmortization":              "D&A",

    # ---- Balance Sheet ----
    "totalAssets":                              "Total Assets",
    "totalCurrentAssets":                       "Current Assets",
    "totalNonCurrentAssets":                    "Non-Current Assets",
    "cashAndCashEquivalents":                   "Cash & Equivalents",
    "cashAndShortTermInvestments":              "Cash & Short-Term Investments",
    "shortTermInvestments":                     "Short-Term Investments",
    "netReceivables":                           "Receivables",
    "inventory":                                "Inventory",
    "propertyPlantEquipmentNet":                "PP&E (net)",
    "goodwill":                                 "Goodwill",
    "intangibleAssets":                         "Intangible Assets",
    "goodwillAndIntangibleAssets":              "Goodwill & Intangibles",
    "longTermInvestments":                      "Long-Term Investments",
    "otherAssets":                              "Other Assets",
    "totalLiabilities":                         "Total Liabilities",
    "totalCurrentLiabilities":                  "Current Liabilities",
    "totalNonCurrentLiabilities":               "Non-Current Liabilities",
    "accountPayables":                          "Accounts Payable",
    "shortTermDebt":                            "Short-Term Debt",
    "longTermDebt":                             "Long-Term Debt",
    "totalDebt":                                "Total Debt",
    "deferredRevenue":                          "Deferred Revenue",
    "otherLiabilities":                         "Other Liabilities",
    "totalStockholdersEquity":                  "Stockholders Equity",
    "totalEquity":                              "Total Equity",
    "retainedEarnings":                         "Retained Earnings",
    "commonStock":                              "Common Stock",
    "commonStockSharesOutstanding":             "Shares Outstanding",

    # ---- Cash Flow Statement ----
    "operatingCashFlow":                        "Operating Cash Flow",
    "netCashProvidedByOperatingActivities":     "Operating Cash Flow",
    "capitalExpenditure":                       "CapEx",
    "freeCashFlow":                             "Free Cash Flow",
    "stockBasedCompensation":                   "Stock-Based Comp",
    "dividendsPaid":                            "Dividends Paid",
    "commonStockRepurchased":                   "Buybacks",
    "stockRepurchase":                          "Buybacks",
    "acquisitionsNet":                          "Acquisitions",
    "netCashUsedForInvestingActivites":         "Net Investing CF",
    "netCashUsedProvidedByFinancingActivities": "Net Financing CF",
    "changeInWorkingCapital":                   "Δ Working Capital",
    "debtRepayment":                            "Debt Repayment",
    "commonStockIssued":                        "Common Stock Issued",
}


def get_label(key: str) -> str:
    """Pretty label for a raw camelCase / snake_case field name."""
    if key in ACCOUNT_LABELS:
        return ACCOUNT_LABELS[key]
    # Already-human input ("Total Revenue") — pass through unchanged.
    if " " in key or key.istitle():
        return key
    # Fallback: split camelCase → Title Case.
    spaced = re.sub(r"(?<!^)([A-Z])", r" \1", key).strip()
    return spaced.replace("_", " ").title()


# ============================================================
# Per-statement display order + subtotal flags
#
# Each entry is (key, kind) where kind ∈ {"row", "subtotal", "section"}.
#   row       → ordinary line item
#   subtotal  → drawn with a top border + medium font weight
#   section   → uppercase gold separator (no numeric data)
# ============================================================
INCOME_STATEMENT_ORDER: list[tuple[str, str]] = [
    ("revenue",                                       "row"),
    ("costOfRevenue",                                 "row"),
    ("grossProfit",                                   "subtotal"),
    ("sellingGeneralAndAdministrativeExpenses",       "row"),
    ("researchAndDevelopmentExpenses",                "row"),
    ("operatingExpenses",                             "row"),
    ("operatingIncome",                               "subtotal"),
    ("ebitda",                                        "row"),
    ("interestExpense",                               "row"),
    ("incomeTaxExpense",                              "row"),
    ("netIncome",                                     "subtotal"),
    ("eps",                                           "row"),
    ("epsdiluted",                                    "row"),
    ("weightedAverageShsOut",                         "row"),
]

BALANCE_SHEET_ORDER: list[tuple[str, str]] = [
    ("__assets__",                                    "section"),
    ("cashAndCashEquivalents",                        "row"),
    ("shortTermInvestments",                          "row"),
    ("netReceivables",                                "row"),
    ("inventory",                                     "row"),
    ("totalCurrentAssets",                            "subtotal"),
    ("propertyPlantEquipmentNet",                     "row"),
    ("goodwill",                                      "row"),
    ("intangibleAssets",                              "row"),
    ("longTermInvestments",                           "row"),
    ("totalAssets",                                   "subtotal"),
    ("__liabilities__",                               "section"),
    ("accountPayables",                               "row"),
    ("shortTermDebt",                                 "row"),
    ("totalCurrentLiabilities",                       "subtotal"),
    ("longTermDebt",                                  "row"),
    ("totalDebt",                                     "row"),
    ("totalLiabilities",                              "subtotal"),
    ("__equity__",                                    "section"),
    ("commonStock",                                   "row"),
    ("retainedEarnings",                              "row"),
    ("totalStockholdersEquity",                       "subtotal"),
]

CASH_FLOW_ORDER: list[tuple[str, str]] = [
    ("netIncome",                                     "row"),
    ("depreciationAndAmortization",                   "row"),
    ("stockBasedCompensation",                        "row"),
    ("changeInWorkingCapital",                        "row"),
    ("operatingCashFlow",                             "subtotal"),
    ("capitalExpenditure",                            "row"),
    ("acquisitionsNet",                               "row"),
    ("netCashUsedForInvestingActivites",              "subtotal"),
    ("dividendsPaid",                                 "row"),
    ("commonStockRepurchased",                        "row"),
    ("debtRepayment",                                 "row"),
    ("netCashUsedProvidedByFinancingActivities",      "subtotal"),
    ("freeCashFlow",                                  "subtotal"),
]

# Section headers used by the table renderer when a "section" row appears
SECTION_LABELS: dict[str, str] = {
    "__assets__":      "ASSETS",
    "__liabilities__": "LIABILITIES",
    "__equity__":      "EQUITY",
}


# ============================================================
# HYBRID VIEW — derived rows + analyst-spreadsheet layouts
# ============================================================
DerivedStyle = Literal[
    "yoy",                    # % change vs previous period
    "margin_of_revenue",      # value / revenue
    "of_total_assets",        # value / total assets
    "of_total_liabilities",   # value / total liabilities
    "tax_rate",               # value / ref_row (typically pretax)
    "capex_margin",           # capex / revenue (negative natural)
]


@dataclass(frozen=True)
class DerivedRow:
    """A row computed inline from already-loaded absolute rows."""
    label: str
    style: DerivedStyle
    base_row: str                       # account key the value depends on
    ref_row: Optional[str] = None       # divisor for tax_rate
    indent: int = 1
    color_by_sign: bool = False         # gold/orange instead of muted grey


# ----- Layout = list[(key | DerivedRow, role)] -----
# role ∈ {None, "subtotal", "section_header"}
# Section headers use the legacy "__assets__" sentinel keys.
LayoutEntry = tuple[Union[str, DerivedRow], Optional[str]]


INCOME_STATEMENT_LAYOUT: list[LayoutEntry] = [
    ("revenue", None),
    (DerivedRow("% change YoY", "yoy", "revenue", color_by_sign=True), None),
    ("costOfRevenue", None),
    ("grossProfit", "subtotal"),
    (DerivedRow("% change YoY", "yoy", "grossProfit", color_by_sign=True), None),
    (DerivedRow("% gross margin", "margin_of_revenue", "grossProfit"), None),
    ("researchAndDevelopmentExpenses", None),
    ("sellingGeneralAndAdministrativeExpenses", None),
    ("operatingExpenses", None),
    ("operatingIncome", "subtotal"),
    (DerivedRow("% change YoY", "yoy", "operatingIncome", color_by_sign=True), None),
    (DerivedRow("% operating margin", "margin_of_revenue", "operatingIncome"), None),
    ("interestIncome", None),
    ("interestExpense", None),
    ("depreciationAndAmortization", None),
    ("incomeBeforeTax", "subtotal"),
    ("incomeTaxExpense", None),
    (DerivedRow("% effective tax rate", "tax_rate",
                "incomeTaxExpense", "incomeBeforeTax"), None),
    ("netIncome", "subtotal"),
    (DerivedRow("% change YoY", "yoy", "netIncome", color_by_sign=True), None),
    (DerivedRow("% net margin", "margin_of_revenue", "netIncome"), None),
    ("ebitda", None),
    (DerivedRow("% change YoY", "yoy", "ebitda", color_by_sign=True), None),
    (DerivedRow("% EBITDA margin", "margin_of_revenue", "ebitda"), None),
    ("weightedAverageShsOut", None),
    (DerivedRow("% change YoY", "yoy", "weightedAverageShsOut",
                color_by_sign=True), None),
    ("epsdiluted", None),
]


BALANCE_SHEET_LAYOUT: list[LayoutEntry] = [
    ("__assets__", "section_header"),
    ("cashAndCashEquivalents", None),
    ("netReceivables", None),
    ("inventory", None),
    ("totalCurrentAssets", "subtotal"),
    (DerivedRow("% of total assets", "of_total_assets", "totalCurrentAssets"), None),
    ("propertyPlantEquipmentNet", None),
    ("goodwill", None),
    ("intangibleAssets", None),
    ("totalNonCurrentAssets", "subtotal"),
    (DerivedRow("% of total assets", "of_total_assets",
                "totalNonCurrentAssets"), None),
    ("totalAssets", "subtotal"),
    (DerivedRow("% change YoY", "yoy", "totalAssets", color_by_sign=True), None),

    ("__liabilities__", "section_header"),
    ("accountPayables", None),
    ("shortTermDebt", None),
    ("totalCurrentLiabilities", "subtotal"),
    (DerivedRow("% of total liabilities", "of_total_liabilities",
                "totalCurrentLiabilities"), None),
    ("longTermDebt", None),
    ("totalNonCurrentLiabilities", "subtotal"),
    (DerivedRow("% of total liabilities", "of_total_liabilities",
                "totalNonCurrentLiabilities"), None),
    ("totalLiabilities", "subtotal"),
    (DerivedRow("% change YoY", "yoy", "totalLiabilities", color_by_sign=True), None),

    ("__equity__", "section_header"),
    ("totalStockholdersEquity", "subtotal"),
    (DerivedRow("% change YoY", "yoy", "totalStockholdersEquity",
                color_by_sign=True), None),
]


CASH_FLOW_LAYOUT: list[LayoutEntry] = [
    ("operatingCashFlow", "subtotal"),
    (DerivedRow("% change YoY", "yoy", "operatingCashFlow",
                color_by_sign=True), None),
    (DerivedRow("% CFO margin", "margin_of_revenue", "operatingCashFlow"), None),
    ("capitalExpenditure", None),
    (DerivedRow("% capex margin", "capex_margin", "capitalExpenditure"), None),
    ("freeCashFlow", "subtotal"),
    (DerivedRow("% change YoY", "yoy", "freeCashFlow", color_by_sign=True), None),
    (DerivedRow("% FCF margin", "margin_of_revenue", "freeCashFlow"), None),
    ("stockBasedCompensation", None),
    ("dividendsPaid", None),
    ("commonStockRepurchased", None),
    ("acquisitionsNet", None),
]


# Account keys that get a CAGR column rendered (5Y / 10Y).
CAGR_ELIGIBLE_ROWS: set[str] = {
    "revenue", "grossProfit", "operatingIncome", "netIncome",
    "ebitda", "epsdiluted", "operatingCashFlow", "freeCashFlow",
    "totalAssets", "totalStockholdersEquity",
}


__all__ = [
    "ACCOUNT_LABELS", "get_label",
    "INCOME_STATEMENT_ORDER", "BALANCE_SHEET_ORDER", "CASH_FLOW_ORDER",
    "INCOME_STATEMENT_LAYOUT", "BALANCE_SHEET_LAYOUT", "CASH_FLOW_LAYOUT",
    "CAGR_ELIGIBLE_ROWS",
    "SECTION_LABELS",
    "DerivedRow", "DerivedStyle",
]
