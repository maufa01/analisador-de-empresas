"""
JPMorgan Chase (JPM) — calendar year financials.

Banks have a non-standard income statement (net interest income, no
"revenue" / "COGS" in the industrial sense) and a giant balance sheet.
We map total revenue (managed) → revenue field for our ratio plumbing.
"""
from __future__ import annotations
import pandas as pd


def income() -> pd.DataFrame:
    rows = [
        {
            "date": "2022-12-31",
            "revenue":             132_290_000_000,   # total net revenue
            "costOfRevenue":                     0,    # banks N/A
            "grossProfit":         132_290_000_000,
            "sellingGeneralAndAdministrativeExpenses": 76_140_000_000,
            "operatingIncome":      46_166_000_000,
            "ebit":                 46_166_000_000,
            "ebitda":               46_166_000_000,
            "interestExpense":      26_098_000_000,
            "incomeTaxExpense":      8_490_000_000,
            "netIncome":            37_676_000_000,
            "eps":                   12.09,
            "weightedAverageShsOut": 2_965_000_000,
        },
        {
            "date": "2023-12-31",
            "revenue":             158_104_000_000,
            "costOfRevenue":                     0,
            "grossProfit":         158_104_000_000,
            "sellingGeneralAndAdministrativeExpenses": 87_172_000_000,
            "operatingIncome":      61_610_000_000,
            "ebit":                 61_610_000_000,
            "ebitda":               61_610_000_000,
            "interestExpense":      81_300_000_000,
            "incomeTaxExpense":     12_060_000_000,
            "netIncome":            49_552_000_000,
            "eps":                   16.23,
            "weightedAverageShsOut": 2_886_000_000,
        },
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def balance() -> pd.DataFrame:
    rows = [
        {
            "date": "2022-12-31",
            "totalAssets":             3_665_743_000_000,
            "totalLiabilities":        3_373_000_000_000,
            "totalStockholdersEquity":   292_332_000_000,
            "totalDebt":                 511_320_000_000,
            "longTermDebt":              295_865_000_000,
            "shortTermDebt":             215_455_000_000,
            "cashAndCashEquivalents":    567_227_000_000,
            "totalCurrentAssets":      3_665_743_000_000,   # banks N/A
            "totalCurrentLiabilities": 3_373_000_000_000,
            "propertyPlantEquipmentNet": 27_734_000_000,
            "netReceivables":          1_135_647_000_000,   # loans
            "inventory":                            0,
            "goodwill":                  51_662_000_000,
            "intangibleAssets":           1_454_000_000,
        },
        {
            "date": "2023-12-31",
            "totalAssets":             3_875_393_000_000,
            "totalLiabilities":        3_547_000_000_000,
            "totalStockholdersEquity":   327_878_000_000,
            "totalDebt":                 391_676_000_000,
            "longTermDebt":              296_877_000_000,
            "shortTermDebt":              94_799_000_000,
            "cashAndCashEquivalents":    624_184_000_000,
            "totalCurrentAssets":      3_875_393_000_000,
            "totalCurrentLiabilities": 3_547_000_000_000,
            "propertyPlantEquipmentNet": 30_157_000_000,
            "netReceivables":          1_323_706_000_000,
            "inventory":                            0,
            "goodwill":                  52_173_000_000,
            "intangibleAssets":           1_434_000_000,
        },
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def cash_flow() -> pd.DataFrame:
    rows = [
        {
            "date": "2022-12-31",
            "operatingCashFlow":              107_119_000_000,
            "capitalExpenditure":              -7_726_000_000,
            "stockBasedCompensation":           4_466_000_000,
            "depreciationAndAmortization":      8_625_000_000,
            "freeCashFlow":                    99_393_000_000,
            "netCashUsedForInvestingActivites": -73_750_000_000,
            "netCashUsedProvidedByFinancingActivities": -47_521_000_000,
        },
        {
            "date": "2023-12-31",
            "operatingCashFlow":               25_077_000_000,
            "capitalExpenditure":              -7_634_000_000,
            "stockBasedCompensation":           5_064_000_000,
            "depreciationAndAmortization":      9_033_000_000,
            "freeCashFlow":                    17_443_000_000,
            "netCashUsedForInvestingActivites":  84_572_000_000,
            "netCashUsedProvidedByFinancingActivities": -113_510_000_000,
        },
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()
