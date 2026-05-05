"""
One-shot bootstrap script — creates the full file tree for equity_app/
with one-line docstrings indicating what each module is responsible for.

Idempotent: existing files are NOT overwritten. Run:
    python scripts/_scaffold.py
from inside the equity_app/ directory.
"""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# packages where we want an __init__.py
PACKAGES = [
    "core", "data", "analysis", "valuation", "scoring", "portfolio",
    "ui", "ui/components", "ui/charts",
    "exports", "tests", "tests/fixtures", "scripts",
]

# pages/ uses Streamlit's auto-discovery and does NOT need __init__.py
NON_PACKAGES = ["pages"]

# (relative_path, docstring) — files are skeleton-only
FILES: dict[str, str] = {
    # ---------- core ----------
    "core/config.py": "Pydantic-Settings: environment-driven application configuration. Loaded once at import time.",
    "core/constants.py": "Financial constants: WACC defaults, scoring weights, sector lists, cache TTLs, literal user-facing messages.",
    "core/exceptions.py": "Custom exception hierarchy. TickerNotFoundError carries the literal user-facing message defined in requirements.",
    "core/logging.py": "Structlog configuration (JSON or console renderer depending on settings).",

    # ---------- data ----------
    "data/base.py": "DataProvider abstract interface, CompanyData and Quote dataclasses shared across providers.",
    "data/finviz_provider.py": "Finviz provider via finvizfinance: real-time quotes, fundamentals, screener, news, insider transactions.",
    "data/fmp_provider.py": "Financial Modeling Prep provider: 10y income/balance/cash-flow, profile, peers, historical prices.",
    "data/fred_provider.py": "FRED provider via pandas-datareader: risk-free rate (10Y Treasury), FX rates, macro indicators.",
    "data/edgar_provider.py": "SEC EDGAR provider: 10-K filings (qualitative analysis) and Form 4 (insider transactions).",
    "data/yfinance_provider.py": "Yfinance provider: fallback-only when other sources fail.",
    "data/cache.py": "Diskcache wrapper + cached() decorator with namespaced TTLs. Switches to Redis when CACHE_BACKEND=redis.",
    "data/rate_limiter.py": "pyrate-limiter wrapper plus MinDelayLimiter for polite scrapers (Finviz). Decorator with_limiter().",
    "data/currency.py": "FX conversion utilities, used to normalize foreign-currency financials to USD.",

    # ---------- analysis ----------
    "analysis/ratios.py": "Standard + adjusted ratios. FCF AJUSTADO POR SBC, ROIC vs WACC, cash-conversion, all margins.",
    "analysis/earnings_quality.py": "Beneish M-Score, Piotroski F-Score, Sloan ratio. Output: red/yellow/green flags with explanation.",
    "analysis/fundamentals_check.py": "Coherence validation: balance sheet must balance; cash-flow tied to BS deltas; flag inconsistencies.",
    "analysis/balance_sheet_quality.py": "Goodwill / intangibles / off-balance-sheet items / pension obligations / customer concentration.",
    "analysis/capital_allocation.py": "Buybacks vs market cap, dividend payout sustainability, M&A returns, ROIC on incremental capital.",
    "analysis/insider_analysis.py": "Form 4 patterns: net buying/selling, cluster buys, CEO/CFO patterns, compensation alignment.",
    "analysis/short_interest.py": "Short interest from Finviz: borrow data, days-to-cover, squeeze risk indicators.",
    "analysis/news_sentiment.py": "FinBERT sentiment over Finviz news headlines, with VADER fallback for speed.",
    "analysis/wacc.py": "Beta via OLS regression (statsmodels), Hamada de/relevering, real cost of debt, market-value capital structure.",
    "analysis/industry_classifier.py": "Normalizes provider sector/industry strings to GICS taxonomy (11 sectors).",
    "analysis/damodaran_loader.py": "Loads industry benchmarks (margins, betas, ERP) from Damodaran's NYU public datasets.",

    # ---------- valuation ----------
    "valuation/dcf_three_stage.py": "Three-stage DCF (high growth → fade → terminal). Sensitivity heatmap WACC × g.",
    "valuation/monte_carlo.py": "Vectorized 10k Monte Carlo over revenue growth, EBITDA margin, WACC, terminal growth.",
    "valuation/reverse_dcf.py": "Solves implied growth rate that justifies the current market price.",
    "valuation/comparables.py": "Peers from FMP, multiples with IQR/winsorization filtering, growth/size/margin adjustments.",
    "valuation/residual_income.py": "Residual Income model — preferred for financials where DCF performs poorly.",
    "valuation/ddm.py": "Dividend Discount Model: Gordon and multi-stage. Auto-detection of applicability.",
    "valuation/valuation_aggregator.py": "Combines the 5 models with sector-specific weights; returns range + confidence level.",

    # ---------- scoring ----------
    "scoring/scorer.py": "Sector-normalized scoring (percentiles within sector). Components: growth, profitability, solvency, EQ, valuation.",
    "scoring/rating.py": "STRONG BUY / BUY / HOLD / SELL / STRONG SELL with confidence based on dispersion across valuation models.",

    # ---------- portfolio ----------
    "portfolio/optimizer.py": "PyPortfolioOpt wrapper: max-sharpe, min-vol, sortino, equal-weight, HRP.",
    "portfolio/black_litterman.py": "Black-Litterman with user views, equilibrium implied returns, view confidence matrix.",
    "portfolio/shrinkage.py": "Ledoit-Wolf shrinkage (sklearn.covariance.LedoitWolf) and exponentially-weighted covariance.",
    "portfolio/constraints.py": "Position size limits, sector caps, turnover constraints, long-only/short, country caps.",
    "portfolio/garch_volatility.py": "GARCH(1,1) via arch library; produces forward volatility forecasts for VaR.",
    "portfolio/var_calculator.py": "Parametric/Historic/Monte-Carlo VaR-95% and CVaR (Expected Shortfall).",
    "portfolio/backtest.py": "Walk-forward, point-in-time backtester. Compares against S&P500, equal-weight, 60/40.",

    # ---------- ui/components ----------
    "ui/components/realtime_quote.py": "st.fragment(run_every=N) component for auto-refreshing real-time quotes from Finviz.",
    "ui/components/valuation_card.py": "Reusable terminal-style valuation card (label, value, accent, sub).",
    "ui/components/monte_carlo_chart.py": "Histogram of Monte Carlo intrinsic-value distribution with percentile markers.",
    "ui/components/peer_comparison.py": "Peer table with target row highlighted + radar chart comparison.",
    "ui/components/score_breakdown.py": "Sector-normalized score breakdown bars with sector medians overlaid.",
    "ui/components/alert_badge.py": "Earnings-quality flag badge (green/yellow/red) with hover explanation.",

    # ---------- ui/charts ----------
    "ui/charts/revenue_history.py": "Plotly bar chart of 10y revenue history with CAGR overlay.",
    "ui/charts/margins_evolution.py": "Plotly line chart of gross/operating/net/EBITDA margins over 10y.",
    "ui/charts/price_vs_intrinsic.py": "Price line vs intrinsic horizontal line vs Monte-Carlo bands.",
    "ui/charts/monte_carlo_distribution.py": "Histogram of MC intrinsic distribution with current price marker.",
    "ui/charts/sensitivity_heatmap.py": "DCF sensitivity heatmap WACC × terminal growth.",
    "ui/charts/efficient_frontier.py": "Efficient frontier with individual assets, max-sharpe, min-vol markers.",
    "ui/charts/drawdown_chart.py": "Equity curve + underwater drawdown chart for backtest results.",

    "ui/styles.py": "Bloomberg-style CSS constants and inject_css() helper used across pages.",

    # ---------- exports ----------
    "exports/pdf_report.py": "Full equity-research PDF report via reportlab.",
    "exports/excel_export.py": "Multi-sheet Excel export (financials, valuations, peers) via openpyxl.",

    # ---------- tests ----------
    "tests/conftest.py": "Pytest fixtures: sample financials (AAPL FY2023, MSFT FY2023, JPM FY2023) and stub providers.",
    "tests/fixtures/__init__.py": "Test data fixtures package.",
    "tests/test_ratios.py": "Property-based and snapshot tests for ratios.",
    "tests/test_dcf.py": "DCF monotonicity (intrinsic decreases with WACC) and value matches Bloomberg within 1%.",
    "tests/test_monte_carlo.py": "Monte Carlo: convergence, distribution shape, percentile correctness.",
    "tests/test_comparables.py": "Comparables filtering (IQR, winsorize) and median behavior under outliers.",
    "tests/test_earnings_quality.py": "Beneish/Piotroski/Sloan against published examples.",
    "tests/test_wacc.py": "Beta regression, Hamada relevering, market-value capital structure.",
    "tests/test_portfolio.py": "Sum-of-weights = 1, max-sharpe vs min-vol Sharpe ranking, constraint enforcement.",
    "tests/test_finviz_provider.py": "Finviz provider unit tests with mocked finvizfinance responses.",
    "tests/test_fmp_provider.py": "FMP provider unit tests with mocked HTTP responses.",
    "tests/test_ticker_not_found.py": "Verifies the LITERAL error message — see requirements section 3, rule #1.",

    # ---------- scripts ----------
    "scripts/load_damodaran_data.py": "Downloads and caches Damodaran's industry datasets (margins, betas, ERP).",
    "scripts/precompute_sectors.py": "Pre-computes sector medians used by the sector-normalized scorer.",
    "scripts/seed_watchlist.py": "Seeds the local SQLite watchlist with example tickers.",

    # ---------- pages (Streamlit auto-discovers) ----------
    "pages/1_📊_Stock_Analysis.py": "Streamlit page: stock analysis (overview, financials, valuation, quality, peers, insiders, news).",
    "pages/2_🔍_Screener.py": "Streamlit page: Finviz screener with sector/industry/metric filters and bulk actions.",
    "pages/3_📈_Portfolio_Optimizer.py": "Streamlit page: Markowitz/BL/HRP optimization with constraints and backtest.",
    "pages/4_⭐_Watchlist.py": "Streamlit page: persistent watchlist (SQLite) with real-time quotes and alert configuration.",
    "pages/5_⚖️_Compare.py": "Streamlit page: side-by-side comparison of up to 5 tickers.",
    "pages/6_🧪_Backtester.py": "Streamlit page: walk-forward backtest of the scoring system, no look-ahead bias.",

    # ---------- root ----------
    "app.py": "Streamlit entry-point: configures global styles and renders home/landing page; pages/ are auto-discovered.",
    "Dockerfile": "Multi-stage Dockerfile for the Streamlit app.",
    "docker-compose.yml": "Compose stack: streamlit-app + redis + scheduler (APScheduler).",
    ".env.example": "Example environment file documenting all configurable variables.",
    ".pre-commit-config.yaml": "Pre-commit hooks: ruff, black, mypy, end-of-file-fixer, etc.",
}


def main() -> None:
    for pkg in PACKAGES:
        p = ROOT / pkg
        p.mkdir(parents=True, exist_ok=True)
        init = p / "__init__.py"
        if not init.exists():
            init.write_text(f'"""{pkg.replace("/", ".")} package."""\n')
    for d in NON_PACKAGES:
        (ROOT / d).mkdir(parents=True, exist_ok=True)

    created = 0
    for rel, doc in FILES.items():
        p = ROOT / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            continue
        if rel.endswith(".py"):
            p.write_text(f'"""{doc}\n\nTODO: implement.\n"""\n')
        elif rel.endswith(".yml") or rel.endswith(".yaml"):
            p.write_text(f"# {doc}\n# TODO: implement.\n")
        elif rel == "Dockerfile":
            p.write_text(f"# {doc}\n# TODO: implement.\n")
        elif rel == ".env.example":
            p.write_text(f"# {doc}\n")
        else:
            p.write_text(f"# {doc}\n")
        created += 1
    print(f"scaffold ok — {created} new files")


if __name__ == "__main__":
    main()
