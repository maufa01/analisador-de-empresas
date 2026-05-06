"""
GAAP concept aliases for non-standard sectors (banks, REITs, insurance).

Why this exists: ``data/edgar_provider.py``'s ``_GAAP_ALIASES`` table is
tuned for non-financial issuers — it expects ``Revenues`` /
``CostOfRevenue`` / ``OperatingIncomeLoss``. For a bank, those tags are
sparsely populated; the right concepts are ``InterestIncomeOperating``,
``ProvisionForLoanLeaseAndOtherLosses``, etc.

Each constant below is a plain ``{logical_key: [GAAP_alias, ...]}`` map.
The sector analyzers (``analysis/bank_analysis.py`` etc.) walk the
aliases in order and use the first one that has any reported values for
the ticker.
"""
from __future__ import annotations
from typing import Optional


# ============================================================
# Banks
# ============================================================
BANK_INCOME_CONCEPTS: dict[str, list[str]] = {
    "interest_income": [
        "InterestAndDividendIncomeOperating",
        "InterestIncomeOperating",
        "InterestAndFeeIncomeLoansAndLeases",
        "InterestIncome",
    ],
    "interest_expense": [
        "InterestExpense",
        "InterestExpenseDeposits",
    ],
    "net_interest_income": [
        "InterestIncomeExpenseNet",
        "InterestIncomeExpenseAfterProvisionForLoanLoss",
    ],
    "provision_for_loan_losses": [
        "ProvisionForLoanLeaseAndOtherLosses",
        "ProvisionForLoanAndLeaseLosses",
        "ProvisionForCreditLossesNet",
        "ProvisionForCreditLosses",
    ],
    "noninterest_income": [
        "NoninterestIncome",
    ],
    "noninterest_expense": [
        "NoninterestExpense",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
    ],
    "shares_diluted": [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
    ],
}

BANK_BALANCE_CONCEPTS: dict[str, list[str]] = {
    "total_loans": [
        "LoansAndLeasesReceivableNetReportedAmount",
        "FinancingReceivableExcludingAccruedInterestAfterAllowanceForCreditLoss",
        "FinancingReceivableNet",
        "LoansAndLeasesReceivableNetOfDeferredIncome",
    ],
    "total_deposits": [
        "Deposits",
        "DepositsTotal",
        "DepositLiabilities",
    ],
    "total_assets":   ["Assets"],
    "total_equity":   ["StockholdersEquity"],
}


# ============================================================
# REITs
# ============================================================
REIT_INCOME_CONCEPTS: dict[str, list[str]] = {
    "rental_income": [
        "OperatingLeaseLeaseIncome",
        "OperatingLeaseIncome",
        "RentalIncomeNonoperating",
        "Revenues",
    ],
    "operating_expenses": [
        "OperatingExpenses",
    ],
    "depreciation": [
        "DepreciationAndAmortization",
        "Depreciation",
        "DepreciationDepletionAndAmortization",
    ],
    "net_income": [
        "NetIncomeLoss",
    ],
    "gain_on_sale": [
        "GainLossOnSaleOfPropertiesNetOfApplicableIncomeTaxes",
        "GainLossOnSaleOfPropertyPlantEquipment",
        "GainLossOnDispositionOfRealEstateInvestmentTrustNetOfApplicableIncomeTaxes",
    ],
    "shares_diluted": [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
    ],
}

REIT_BALANCE_CONCEPTS: dict[str, list[str]] = {
    "real_estate_investments": [
        "RealEstateInvestmentPropertyNet",
        "RealEstateInvestmentPropertyAtCost",
        "InvestmentBuildingAndBuildingImprovements",
    ],
    "total_assets":  ["Assets"],
    "total_equity":  ["StockholdersEquity"],
}

REIT_CASHFLOW_CONCEPTS: dict[str, list[str]] = {
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsForCapitalImprovements",
    ],
    "dividends_paid": [
        "PaymentsOfDividends",
        "PaymentsOfDividendsCommonStock",
    ],
}


# ============================================================
# Insurance
# ============================================================
INSURANCE_INCOME_CONCEPTS: dict[str, list[str]] = {
    "premium_revenue": [
        "PremiumsEarnedNet",
        "PremiumsWrittenNet",
        "InsurancePremiumsEarnedAndOther",
    ],
    "investment_income": [
        "NetInvestmentIncome",
        "InvestmentIncomeNet",
    ],
    "policyholder_benefits": [
        "PolicyholderBenefitsAndClaimsIncurredNet",
    ],
    "underwriting_expense": [
        "DeferredPolicyAcquisitionCostsAmortizationExpense",
    ],
    "net_income": ["NetIncomeLoss"],
}


def get_concepts_for_sector(ticker_type: str) -> dict:
    """Return ``{income, balance[, cashflow], type}`` keyed alias maps."""
    if ticker_type == "us_common_bank":
        return {
            "income": BANK_INCOME_CONCEPTS,
            "balance": BANK_BALANCE_CONCEPTS,
            "type": "bank",
        }
    if ticker_type == "us_common_reit":
        return {
            "income": REIT_INCOME_CONCEPTS,
            "balance": REIT_BALANCE_CONCEPTS,
            "cashflow": REIT_CASHFLOW_CONCEPTS,
            "type": "reit",
        }
    if ticker_type == "us_common_insurance":
        return {
            "income": INSURANCE_INCOME_CONCEPTS,
            "type": "insurance",
        }
    return {"type": "standard"}
