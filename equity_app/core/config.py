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
