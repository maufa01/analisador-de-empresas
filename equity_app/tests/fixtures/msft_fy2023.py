"""
Microsoft (MSFT) — fiscal years ending June 30.

FY2022 and FY2023 only (sufficient for two-period earnings-quality
checks). FMP-shape columns.
"""
from __future__ import annotations
import pandas as pd


def income() -> pd.DataFrame:
    rows = [
        {
            "date": "2022-06-30",
            "revenue":            198_270_000_000,
            "costOfRevenue":       62_650_000_000,
            "grossProfit":        135_620_000_000,
            "sellingGeneralAndAdministrativeExpenses": 27_725_000_000,
            "operatingIncome":     83_383_000_000,
            "ebit":                83_383_000_000,
            "ebitda":             100_239_000_000,
            "interestExpense":      2_063_000_000,
            "incomeTaxExpense":    10_978_000_000,
            "netIncome":           72_738_000_000,
            "eps":                  9.70,
            "weightedAverageShsOut": 7_500_000_000,
        },
        {
            "date": "2023-06-30",
            "revenue":            211_915_000_000,
            "costOfRevenue":       65_863_000_000,
            "grossProfit":        146_052_000_000,
            "sellingGeneralAndAdministrativeExpenses": 30_334_000_000,
            "operatingIncome":     88_523_000_000,
            "ebit":                88_523_000_000,
            "ebitda":             105_140_000_000,
            "interestExpense":      1_968_000_000,
            "incomeTaxExpense":    16_950_000_000,
            "netIncome":           72_361_000_000,
            "eps":                  9.72,
            "weightedAverageShsOut": 7_446_000_000,
        },
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def balance() -> pd.DataFrame:
    rows = [
        {
            "date": "2022-06-30",
            "totalAssets":              364_840_000_000,
            "totalLiabilities":         198_298_000_000,
            "totalStockholdersEquity":  166_542_000_000,
            "totalDebt":                 78_383_000_000,
            "longTermDebt":              47_032_000_000,
            "shortTermDebt":              2_749_000_000,
            "cashAndCashEquivalents":    13_931_000_000,
            "totalCurrentAssets":       169_684_000_000,
            "totalCurrentLiabilities":   95_082_000_000,
            "propertyPlantEquipmentNet": 74_398_000_000,
            "netReceivables":            44_261_000_000,
            "inventory":                  3_742_000_000,
            "goodwill":                  67_524_000_000,
            "intangibleAssets":          11_298_000_000,
        },
        {
            "date": "2023-06-30",
            "totalAssets":              411_976_000_000,
            "totalLiabilities":         205_753_000_000,
            "totalStockholdersEquity":  206_223_000_000,
            "totalDebt":                 79_440_000_000,
            "longTermDebt":              41_990_000_000,
            "shortTermDebt":              5_247_000_000,
            "cashAndCashEquivalents":    34_704_000_000,
            "totalCurrentAssets":       184_257_000_000,
            "totalCurrentLiabilities":  104_149_000_000,
            "propertyPlantEquipmentNet": 95_641_000_000,
            "netReceivables":            48_688_000_000,
            "inventory":                  2_500_000_000,
            "goodwill":                  67_886_000_000,
            "intangibleAssets":           9_366_000_000,
        },
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def cash_flow() -> pd.DataFrame:
    rows = [
        {
            "date": "2022-06-30",
            "operatingCashFlow":              89_035_000_000,
            "capitalExpenditure":            -23_886_000_000,
            "stockBasedCompensation":          7_502_000_000,
            "depreciationAndAmortization":    14_460_000_000,
            "freeCashFlow":                   65_149_000_000,
            "netCashUsedForInvestingActivites": -30_311_000_000,
            "netCashUsedProvidedByFinancingActivities": -58_876_000_000,
        },
        {
            "date": "2023-06-30",
            "operatingCashFlow":              87_582_000_000,
            "capitalExpenditure":            -28_107_000_000,
            "stockBasedCompensation":          9_611_000_000,
            "depreciationAndAmortization":    13_861_000_000,
            "freeCashFlow":                   59_475_000_000,
            "netCashUsedForInvestingActivites": -22_680_000_000,
            "netCashUsedProvidedByFinancingActivities": -43_935_000_000,
        },
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()
