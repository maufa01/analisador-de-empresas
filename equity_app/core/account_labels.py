"""
Pretty labels for FMP / yfinance camelCase financial statement fields.

Plus per-statement "row order + subtotal markers" used by the financial
table renderer to draw hierarchy (Revenue → Gross Profit → Operating
Income → Net Income, etc.).
"""
from __future__ import annotations
import re
from typing import Optional


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


__all__ = [
    "ACCOUNT_LABELS", "get_label",
    "INCOME_STATEMENT_ORDER", "BALANCE_SHEET_ORDER", "CASH_FLOW_ORDER",
    "SECTION_LABELS",
]
