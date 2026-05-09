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
    # Stand-in for environments without pydantic-settings (e.g. Streamlit
    # Cloud when the dep isn't pinned). Reads os.environ lazily on every
    # attribute access so secrets hydrated by
    # `_hydrate_env_from_streamlit_secrets` are picked up at use time, not
    # frozen at import time.
    class _Stub:
        # Coerce-helpers ------------------------------------------------
        @staticmethod
        def _str(name: str, default: str = "") -> str:
            return _os.environ.get(name, default) or default

        @staticmethod
        def _int(name: str, default: int) -> int:
            try:
                return int(_os.environ.get(name) or default)
            except (TypeError, ValueError):
                return default

        @staticmethod
        def _float(name: str, default: float) -> float:
            try:
                return float(_os.environ.get(name) or default)
            except (TypeError, ValueError):
                return default

        # ---- API keys ----
        @property
        def fmp_api_key(self) -> str:        return self._str("FMP_API_KEY")
        @property
        def fred_api_key(self) -> str:       return self._str("FRED_API_KEY")
        @property
        def alpha_vantage_key(self) -> str:  return self._str("ALPHA_VANTAGE_KEY")
        @property
        def marketaux_api_key(self) -> str:  return self._str("MARKETAUX_API_KEY")
        @property
        def finnhub_api_key(self) -> str:    return self._str("FINNHUB_API_KEY")
        @property
        def anthropic_api_key(self) -> str:  return self._str("ANTHROPIC_API_KEY")
        @property
        def sec_user_agent(self) -> str:
            return self._str("SEC_USER_AGENT", "Equity App noreply@example.com")

        # ---- Cache / persistence ----
        @property
        def cache_backend(self) -> str:        return self._str("CACHE_BACKEND", "disk")
        @property
        def redis_url(self) -> str:            return self._str("REDIS_URL", "redis://localhost:6379")
        @property
        def cache_ttl_hours(self) -> int:      return self._int("CACHE_TTL_HOURS", 24)
        @property
        def cache_dir(self) -> str:            return self._str("CACHE_DIR", CACHE_DIR_DEFAULT)
        @property
        def watchlist_db_path(self) -> str:    return self._str("WATCHLIST_DB_PATH", WATCHLIST_DB_DEFAULT)

        # ---- Logging ----
        @property
        def log_level(self) -> str:    return self._str("LOG_LEVEL", "INFO")
        @property
        def log_format(self) -> str:   return self._str("LOG_FORMAT", "json")

        # ---- Rate limits ----
        @property
        def fmp_calls_per_minute(self) -> int:    return self._int("FMP_CALLS_PER_MINUTE", 250)
        @property
        def finviz_delay_seconds(self) -> float:  return self._float("FINVIZ_DELAY_SECONDS", 1.0)
        @property
        def fred_calls_per_minute(self) -> int:   return self._int("FRED_CALLS_PER_MINUTE", 120)
        @property
        def yfinance_delay_seconds(self) -> float:return self._float("YFINANCE_DELAY_SECONDS", 0.5)

        # ---- Defaults ----
        @property
        def default_refresh_interval(self) -> int:  return self._int("DEFAULT_REFRESH_INTERVAL", 5)
        @property
        def default_risk_free(self) -> float:       return self._float("DEFAULT_RISK_FREE", 0.045)
        @property
        def default_erp(self) -> float:             return self._float("DEFAULT_ERP", 0.055)
        @property
        def default_terminal_growth(self) -> float: return self._float("DEFAULT_TERMINAL_GROWTH", 0.025)

        # ---- Provider priority ----
        @property
        def provider_priority(self) -> str:
            return self._str("PROVIDER_PRIORITY", "fmp,finviz,yfinance")

        @property
        def provider_priority_list(self) -> list[str]:
            return [p.strip().lower() for p in self.provider_priority.split(",") if p.strip()]

    settings = _Stub()  # type: ignore
