# equity_app

Institutional-grade equity research, valuation, and portfolio optimization on Streamlit.

> ⚠️ **Status — Session 1 of 6 complete.** Foundations only:
> `core/` (config, constants, exceptions, logging), `data/` (provider interface, Finviz, FMP, cache, rate limiter), and the literal-error-message contract test. Analysis, valuation, portfolio, UI and exports follow in subsequent sessions per the plan in `docs/plan.md` (TODO).

---

## Why a v2

The v1 single-file Streamlit app at the repo root is fine for one-off DCFs but cannot scale to the spec:

- 10 years of fundamentals (FMP) — yfinance only exposes ~4
- Real-time quotes (Finviz with auto-refresh) — yfinance is too slow
- 5 valuation models with sector-aware aggregation
- Earnings-quality detection (Beneish / Piotroski / Sloan)
- PyPortfolioOpt with Black-Litterman and Ledoit-Wolf shrinkage
- Walk-forward backtest with no look-ahead bias

The v2 lives in `equity_app/` as an isolated, layered project.

---

## Quick start

```bash
cd equity_app
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # then fill in FMP_API_KEY
streamlit run app.py        # placeholder until Session 5 lands the UI
```

### Test the literal error-message contract (always runnable)

```bash
cd equity_app
python -m pytest tests/test_ticker_not_found.py -v
```

This single test enforces the exact wording specified in section 3 / rule #1
of the requirements. The test fails the build if anyone ever changes it.

### Run the rest of the test suite (requires deps)

```bash
pip install pytest hypothesis
python -m pytest tests/ -q
```

---

## API keys

| Source | Required? | Get it at                                                                 |
|--------|-----------|---------------------------------------------------------------------------|
| FMP    | yes       | <https://site.financialmodelingprep.com/developer/docs>                   |
| FRED   | optional  | <https://fred.stlouisfed.org/docs/api/api_key.html>                       |
| Alpha Vantage | optional fallback | <https://www.alphavantage.co/support/#api-key>                  |

Finviz, yfinance and SEC EDGAR do **not** require keys.

---

## Architecture

```
equity_app/
├── app.py                   # Streamlit entry — Session 5
├── pages/                   # Multi-page UI (Stock, Screener, Portfolio, …) — Session 5
├── core/                    # ✅ DONE — Settings, constants, exceptions, logging
│   ├── config.py            #     pydantic-settings, .env-driven
│   ├── constants.py         #     ALL business assumptions live here
│   ├── exceptions.py        #     TickerNotFoundError carries the literal message
│   └── logging.py           #     structlog (JSON or console)
├── data/                    # ✅ DONE (Session 1 modules)
│   ├── base.py              #     DataProvider abstract + CompanyData/Quote dataclasses
│   ├── finviz_provider.py   #     Real-time quotes, news, insider, screener
│   ├── fmp_provider.py      #     10y financials + peers + historical prices
│   ├── fred_provider.py     #     Risk-free, FX (Session 2)
│   ├── edgar_provider.py    #     10-K, Form 4 (Session 2+)
│   ├── yfinance_provider.py #     Fallback (Session 2)
│   ├── cache.py             #     diskcache / Redis behind one interface
│   ├── rate_limiter.py      #     pyrate-limiter token bucket + min-delay scraper
│   └── currency.py          #     FX normalization (Session 2)
├── analysis/                # 🚧 Session 2 — ratios, earnings quality, WACC
├── valuation/               # 🚧 Session 3 — DCF 3-stage, Monte Carlo, comps, RI, DDM
├── scoring/                 # 🚧 Session 3 — sector-normalized 0-100 + rating
├── portfolio/               # 🚧 Session 4 — PyPortfolioOpt + BL + Ledoit-Wolf + backtest
├── ui/                      # 🚧 Session 5 — components and Plotly charts
├── exports/                 # 🚧 Session 6 — PDF (reportlab) + Excel (openpyxl)
├── tests/                   # ✅ test_ticker_not_found + provider tests
├── scripts/                 #     scaffold + Damodaran loader + sector precompute
├── Dockerfile               # 🚧 Session 6
├── docker-compose.yml       # 🚧 Session 6 — app + redis + apscheduler
├── pyproject.toml           # ✅ ruff / black / mypy / pytest / coverage configs
├── .pre-commit-config.yaml  # ✅
├── .env.example             # ✅
└── requirements.txt         # ✅
```

### Provider chain

`data.finviz_provider` and `data.fmp_provider` implement the abstract
`DataProvider` interface from `data.base`. The orchestrator (Session 2)
walks the chain configured in `PROVIDER_PRIORITY` (default
`fmp,finviz,yfinance`) and raises `TickerNotFoundError` only when **every**
provider misses — at which point the UI renders the literal message.

### Critical contract: literal error message

Per requirements section 3, rule #1:

```
"perdone, no se agrego la accion"
```

No accents. No suggestions. No extra text.

This string is stored once in [core/constants.py](core/constants.py) as
`TICKER_NOT_FOUND_MESSAGE` and exposed via `core.exceptions.TickerNotFoundError`.
The contract is enforced by `tests/test_ticker_not_found.py` — that test
fails the build if anyone ever changes the wording, adds an accent, appends
punctuation, or leaks internal context (ticker, original cause) into
`str(err)`.

### Cache strategy

| Namespace        | TTL          | Source                                              |
|------------------|--------------|-----------------------------------------------------|
| `quote`          | 5 sec        | Finviz / FMP — backs the real-time fragment         |
| `fundamentals`   | 24 h         | FMP profile, key-metrics, ratios; Finviz fundament  |
| `financials`     | 24 h         | FMP 10y income/balance/cashflow                     |
| `news`           | 1 h          | Finviz                                              |
| `insider`        | 6 h          | Finviz                                              |
| `screener`       | 30 min       | Finviz                                              |
| `damodaran`      | 7 days       | Static datasets                                     |
| `beta`           | 7 days       | Computed via OLS regression                         |
| `prices_eod`     | 12 h         | FMP daily prices                                    |

Backend selectable via `CACHE_BACKEND` env var: `disk` (diskcache, default)
or `redis`. Failing imports fall through to an in-process dict cache so
tests run without optional deps.

### Rate limiting

| Provider | Limit                 | Mechanism                              |
|----------|-----------------------|----------------------------------------|
| FMP      | 250 / minute          | Token bucket (pyrate-limiter)          |
| Finviz   | 1 second min delay    | `MinDelayLimiter` polite-scraper guard |
| FRED     | 120 / minute          | Token bucket                           |
| yfinance | 0.5 sec min delay     | `MinDelayLimiter` (Session 2)          |

When `pyrate-limiter` is not installed, a stdlib `_StdlibTokenBucket`
fallback kicks in transparently.

---

## Session plan

| Session | Scope                                                                     | Status     |
|---------|---------------------------------------------------------------------------|------------|
| 1       | core/ + data/ (Finviz, FMP, cache, rate limiter) + tests                  | ✅ done    |
| 2       | analysis/ratios, earnings_quality, fundamentals_check, wacc + fixtures    | pending    |
| 3       | valuation/* (5 models + aggregator) + scoring/                            | pending    |
| 4       | portfolio/* (PyPortfolioOpt + BL + Ledoit-Wolf + backtest)                | pending    |
| 5       | app.py + pages/ + ui/components + ui/charts                               | pending    |
| 6       | exports/, Dockerfile, docker-compose, CI/CD, README final + screenshots   | pending    |

---

## Conventions

- Type-hinted, layered, NO module-level side effects.
- Business assumptions live in `core/constants.py`; runtime knobs in `core/config.py` (.env-driven).
- Layers depend downward only: `analysis` may import from `core` and `data`, never the other way.
- Tests mock at the provider HTTP boundary so CI does not need keys.
- Errors are explicit: `TickerNotFoundError`, `ProviderError`, `RateLimitError`,
  `MissingAPIKeyError`, `DataQualityError`, `ValuationError`,
  `InsufficientDataError` — all under the `EquityAppError` umbrella.

---

## License

MIT.
