"""
Apple Inc. (AAPL) — fiscal years ending late September.

Numbers sourced from 10-K filings (form_type=10-K) for FY2021–FY2023.
Shape matches FMP's annual statements (camelCase). Used by analysis tests
to verify that ratios/earnings-quality/WACC track Bloomberg within 1%.

NOT EXHAUSTIVE — only the line items the analysis layer needs.
"""
from __future__ import annotations
import pandas as pd


def income() -> pd.DataFrame:
    rows = [
        {
            "date": "2021-09-25",
            "revenue":            365_817_000_000,
            "costOfRevenue":      212_981_000_000,
            "grossProfit":        152_836_000_000,
            "sellingGeneralAndAdministrativeExpenses": 21_973_000_000,
            "operatingIncome":    108_949_000_000,
            "ebit":               108_949_000_000,
            "ebitda":             123_136_000_000,
            "interestExpense":      2_645_000_000,
            "incomeTaxExpense":    14_527_000_000,
            "netIncome":           94_680_000_000,
            "eps":                  5.67,
            "weightedAverageShsOut": 16_701_000_000,
        },
        {
            "date": "2022-09-24",
            "revenue":            394_328_000_000,
            "costOfRevenue":      223_546_000_000,
            "grossProfit":        170_782_000_000,
            "sellingGeneralAndAdministrativeExpenses": 25_094_000_000,
            "operatingIncome":    119_437_000_000,
            "ebit":               119_437_000_000,
            "ebitda":             133_138_000_000,
            "interestExpense":      2_931_000_000,
            "incomeTaxExpense":    19_300_000_000,
            "netIncome":           99_803_000_000,
            "eps":                  6.15,
            "weightedAverageShsOut": 16_215_000_000,
        },
        {
            "date": "2023-09-30",
            "revenue":            383_285_000_000,
            "costOfRevenue":      214_137_000_000,
            "grossProfit":        169_148_000_000,
            "sellingGeneralAndAdministrativeExpenses": 24_932_000_000,
            "operatingIncome":    114_301_000_000,
            "ebit":               114_301_000_000,
            "ebitda":             129_564_000_000,
            "interestExpense":      3_933_000_000,
            "incomeTaxExpense":    16_741_000_000,
            "netIncome":           96_995_000_000,
            "eps":                  6.16,
            "weightedAverageShsOut": 15_744_000_000,
        },
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def balance() -> pd.DataFrame:
    rows = [
        {
            "date": "2021-09-25",
            "totalAssets":              351_002_000_000,
            "totalLiabilities":         287_912_000_000,
            "totalStockholdersEquity":   63_090_000_000,
            "totalDebt":                124_719_000_000,
            "longTermDebt":             109_106_000_000,
            "shortTermDebt":             15_613_000_000,
            "cashAndCashEquivalents":    34_940_000_000,
            "totalCurrentAssets":       134_836_000_000,
            "totalCurrentLiabilities":  125_481_000_000,
            "propertyPlantEquipmentNet": 39_440_000_000,
            "netReceivables":            26_278_000_000,
            "inventory":                  6_580_000_000,
            "goodwill":                            0,
            "intangibleAssets":                    0,
        },
        {
            "date": "2022-09-24",
            "totalAssets":              352_755_000_000,
            "totalLiabilities":         302_083_000_000,
            "totalStockholdersEquity":   50_672_000_000,
            "totalDebt":                120_069_000_000,
            "longTermDebt":             110_109_000_000,
            "shortTermDebt":              9_960_000_000,
            "cashAndCashEquivalents":    23_646_000_000,
            "totalCurrentAssets":       135_405_000_000,
            "totalCurrentLiabilities":  153_982_000_000,
            "propertyPlantEquipmentNet": 42_117_000_000,
            "netReceivables":            28_184_000_000,
            "inventory":                  4_946_000_000,
            "goodwill":                            0,
            "intangibleAssets":                    0,
        },
        {
            "date": "2023-09-30",
            "totalAssets":              352_583_000_000,
            "totalLiabilities":         290_437_000_000,
            "totalStockholdersEquity":   62_146_000_000,
            "totalDebt":                111_088_000_000,
            "longTermDebt":             106_550_000_000,
            "shortTermDebt":              4_538_000_000,
            "cashAndCashEquivalents":    29_965_000_000,
            "totalCurrentAssets":       143_566_000_000,
            "totalCurrentLiabilities":  145_308_000_000,
            "propertyPlantEquipmentNet": 43_715_000_000,
            "netReceivables":            29_508_000_000,
            "inventory":                  6_331_000_000,
            "goodwill":                            0,
            "intangibleAssets":                    0,
        },
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def cash_flow() -> pd.DataFrame:
    rows = [
        {
            "date": "2021-09-25",
            "operatingCashFlow":              104_038_000_000,
            "capitalExpenditure":             -11_085_000_000,
            "stockBasedCompensation":           7_906_000_000,
            "depreciationAndAmortization":     11_284_000_000,
            "freeCashFlow":                    92_953_000_000,
            "netCashUsedForInvestingActivites": -14_545_000_000,
            "netCashUsedProvidedByFinancingActivities": -93_353_000_000,
            "dividendsPaid":                  -14_467_000_000,
            "commonStockRepurchased":         -85_971_000_000,
        },
        {
            "date": "2022-09-24",
            "operatingCashFlow":              122_151_000_000,
            "capitalExpenditure":             -10_708_000_000,
            "stockBasedCompensation":           9_038_000_000,
            "depreciationAndAmortization":     11_104_000_000,
            "freeCashFlow":                   111_443_000_000,
            "netCashUsedForInvestingActivites": -22_354_000_000,
            "netCashUsedProvidedByFinancingActivities": -110_749_000_000,
            "dividendsPaid":                  -14_841_000_000,
            "commonStockRepurchased":         -89_402_000_000,
        },
        {
            "date": "2023-09-30",
            "operatingCashFlow":              110_543_000_000,
            "capitalExpenditure":             -10_959_000_000,
            "stockBasedCompensation":          10_833_000_000,
            "depreciationAndAmortization":     11_519_000_000,
            "freeCashFlow":                    99_584_000_000,
            "netCashUsedForInvestingActivites":   3_705_000_000,
            "netCashUsedProvidedByFinancingActivities": -108_488_000_000,
            "dividendsPaid":                  -15_025_000_000,
            "commonStockRepurchased":         -77_550_000_000,
        },
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()
