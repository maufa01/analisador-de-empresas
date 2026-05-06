"""
Pydantic-Settings application configuration.

Loaded once at import time. All values are overridable via environment
variables or a .env file in the project root.

Why pydantic-settings:
- Type validation at boot (no string-to-int bugs at runtime)
- Single source of truth for runtime configuration
- Documents every knob in one place via .env.example
"""
from __future__ import annotations
from typing import Literal
from pathlib import Path

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    from pydantic import Field
    _PYDANTIC_AVAILABLE = True
except ImportError:  # graceful degradation when running tests without deps
    _PYDANTIC_AVAILABLE = False


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR_DEFAULT = str(PROJECT_ROOT / ".cache")
WATCHLIST_DB_DEFAULT = str(PROJECT_ROOT / ".data" / "watchlist.db")


# ============================================================
# Secrets bootstrap — copy st.secrets into os.environ so every reader
# (pydantic-settings, raw os.environ users) sees the same values, no
# matter whether we're running locally with .streamlit/secrets.toml or
# on Streamlit Cloud with the App Settings → Secrets pane.
#
# Runs ONCE at import time. Silent no-op when streamlit isn't loaded
# (e.g. unit tests). Never logs the key VALUES — only the key names
# we picked up — to keep secrets out of stdout / log files.
# ============================================================
import os as _os

_KNOWN_SECRET_KEYS = (
    "SEC_USER_AGENT",
    "FMP_API_KEY",
    "FRED_API_KEY",
    "MARKETAUX_API_KEY",
    "FINNHUB_API_KEY",
    "ALPHA_VANTAGE_KEY",
    "ANTHROPIC_API_KEY",
    "EQUITY_APP_DATA_SOURCE",
)


def _hydrate_env_from_streamlit_secrets() -> None:
    try:
        import streamlit as _st  # type: ignore
    except Exception:
        return
    try:
        secrets = _st.secrets                  # type: ignore[attr-defined]
    except Exception:
        return
    for k in _KNOWN_SECRET_KEYS:
        try:
            v = secrets.get(k)                 # st.secrets supports .get
        except Exception:
            v = None
        if v and k not in _os.environ:
            _os.environ[k] = str(v)


_hydrate_env_from_streamlit_secrets()


def read_secret(name: str, default: str = "") -> str:
    """
    Canonical way to read a secret. Always returns a string.

    Resolution order (first non-empty wins):
        1. ``os.environ[name]`` — populated by:
             - Streamlit Cloud's secret pane → environment
             - ~/.streamlit/secrets.toml hydration above
             - .env file via pydantic-settings
             - explicit shell export
        2. ``default``

    This bypasses the pydantic-settings dependency so it works in
    environments where pydantic-settings isn't installed (CI, local
    venv without dev deps). Never logs the value.
    """
    return _os.environ.get(name, default) or default


if _PYDANTIC_AVAILABLE:

    class Settings(BaseSettings):
        """Single Settings object — read once, used everywhere."""

        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
            case_sensitive=False,
        )

        # ---------- API keys ----------
        fmp_api_key: str = Field(default="", description="Financial Modeling Prep API key.")
        fred_api_key: str = Field(default="", description="FRED API key (optional, public endpoints work without).")
        alpha_vantage_key: str = Field(default="", description="Alpha Vantage key (fallback).")
        marketaux_api_key: str = Field(default="", description="Marketaux news + sentiment.")
        finnhub_api_key: str = Field(default="", description="Finnhub market data + insider tx + news.")
        anthropic_api_key: str = Field(default="", description="Anthropic API for AI thesis generation.")
        sec_user_agent: str = Field(default="Equity App noreply@example.com",
                                    description="SEC EDGAR requires a User-Agent header (no API key).")

        # ---------- Cache ----------
        cache_backend: Literal["disk", "redis"] = "disk"
        redis_url: str = "redis://localhost:6379"
        cache_ttl_hours: int = 24
        cache_dir: str = CACHE_DIR_DEFAULT

        # ---------- Watchlist persistence ----------
        watchlist_db_path: str = WATCHLIST_DB_DEFAULT

        # ---------- Logging ----------
        log_level: str = "INFO"
        log_format: Literal["json", "console"] = "json"

        # ---------- Rate limiting ----------
        fmp_calls_per_minute: int = 250
        finviz_delay_seconds: float = 1.0
        fred_calls_per_minute: int = 120
        yfinance_delay_seconds: float = 0.5

        # ---------- Application defaults ----------
        default_refresh_interval: int = 5
        default_risk_free: float = 0.045
        default_erp: float = 0.055
        default_terminal_growth: float = 0.025

        # ---------- Provider preference ----------
        # Order in which providers are attempted before raising TickerNotFoundError.
        # Comma-separated. Example: "fmp,finviz,yfinance"
        provider_priority: str = "fmp,finviz,yfinance"

        @property
        def provider_priority_list(self) -> list[str]:
            return [p.strip().lower() for p in self.provider_priority.split(",") if p.strip()]

    settings = Settings()

else:
    # Minimal stand-in so that pure-syntax tests can import this module
    # without pydantic installed. Will never run in production.
    class _Stub:
        fmp_api_key = ""
        fred_api_key = ""
        alpha_vantage_key = ""
        marketaux_api_key = ""
        finnhub_api_key = ""
        anthropic_api_key = ""
        sec_user_agent = "Equity App noreply@example.com"
        cache_backend = "disk"
        redis_url = "redis://localhost:6379"
        cache_ttl_hours = 24
        cache_dir = CACHE_DIR_DEFAULT
        watchlist_db_path = WATCHLIST_DB_DEFAULT
        log_level = "INFO"
        log_format = "json"
        fmp_calls_per_minute = 250
        finviz_delay_seconds = 1.0
        fred_calls_per_minute = 120
        yfinance_delay_seconds = 0.5
        default_refresh_interval = 5
        default_risk_free = 0.045
        default_erp = 0.055
        default_terminal_growth = 0.025
        provider_priority = "fmp,finviz,yfinance"
        provider_priority_list = ["fmp", "finviz", "yfinance"]

    settings = _Stub()  # type: ignore
