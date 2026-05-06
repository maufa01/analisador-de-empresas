"""
FRED provider — Federal Reserve Economic Data.

Why direct HTTP instead of pandas-datareader: fewer transitive deps,
explicit rate-limit + key handling, no surprise 5xx on a transitive
upgrade. The FRED API itself is rock-solid.

Public API:
    fetch_series(series_id, *, start=None) → pd.Series
    latest_value(series_id) → (value, observation_date) or (None, None)
    inflation_yoy_pct(series_id="CPIAUCSL") → (yoy_pct, latest_date)
    macro_snapshot() → dict ready to fold into the macro dashboard

Series we care about by default:
    DGS10, DGS2, DGS5, DGS3MO, DGS30 — Treasury yields
    CPIAUCSL, CPILFESL, PCEPI       — inflation indices
    UNRATE                          — unemployment
    SAHMREALTIME                    — Sahm Rule recession indicator
    BAMLH0A0HYM2                    — ICE BofA HY OAS spread
    DFF, DFEDTARU, DFEDTARL         — Fed funds (current + target band)
    DCOILWTICO, GASREGW             — energy
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

import logging
import time

import pandas as pd

from core.config import read_secret

logger = logging.getLogger(__name__)


# ============================================================
# HTTP wrapper with light rate-limit
# ============================================================
_FRED_BASE = "https://api.stlouisfed.org/fred"
_RATE_LIMIT_DELAY = 0.20      # 5 req/s — well under FRED's 120/min default
_last_request_at = 0.0


def _api_key() -> str:
    return read_secret("FRED_API_KEY", "")


def _rate_limit() -> None:
    global _last_request_at
    elapsed = time.time() - _last_request_at
    if elapsed < _RATE_LIMIT_DELAY:
        time.sleep(_RATE_LIMIT_DELAY - elapsed)
    _last_request_at = time.time()


def _fred_get(path: str, params: Optional[dict] = None) -> Any:
    """Returns JSON dict or {} on any failure. Never raises."""
    key = _api_key()
    if not key:
        return {}
    try:
        import requests  # type: ignore
    except ImportError:
        return {}

    _rate_limit()
    full = dict(params or {})
    full["api_key"] = key
    full["file_type"] = "json"
    try:
        r = requests.get(f"{_FRED_BASE}/{path}", params=full, timeout=20)
    except Exception as e:
        logger.debug(f"FRED request failed: {e}")
        return {}
    if r.status_code != 200:
        return {}
    try:
        return r.json()
    except ValueError:
        return {}


# ============================================================
# Series helpers
# ============================================================
def fetch_series(series_id: str, *, start: Optional[str] = None) -> pd.Series:
    """Returns a date-indexed pd.Series (float). Empty on any failure."""
    if not series_id:
        return pd.Series(dtype=float)

    if start is None:
        # 10y of history is enough for every dashboard use
        start = (datetime.utcnow() - timedelta(days=365 * 10)).strftime("%Y-%m-%d")

    payload = _fred_get("series/observations", {
        "series_id":         series_id,
        "observation_start": start,
        "sort_order":        "asc",
    })
    obs = payload.get("observations") if isinstance(payload, dict) else None
    if not obs:
        return pd.Series(dtype=float)

    rows = []
    for o in obs:
        date_str = o.get("date")
        val_str = o.get("value")
        if not date_str or val_str in (None, ".", ""):
            continue
        try:
            rows.append((pd.Timestamp(date_str), float(val_str)))
        except ValueError:
            continue
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series(dict(rows), name=series_id).sort_index()
    return s


def latest_value(series_id: str) -> tuple[Optional[float], Optional[pd.Timestamp]]:
    s = fetch_series(series_id, start=(datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d"))
    if s.empty:
        return None, None
    return float(s.iloc[-1]), s.index[-1]


def inflation_yoy_pct(series_id: str = "CPIAUCSL") -> tuple[Optional[float], Optional[pd.Timestamp]]:
    """YoY % change of an index series (CPIAUCSL = headline CPI)."""
    s = fetch_series(series_id, start=(datetime.utcnow() - timedelta(days=400)).strftime("%Y-%m-%d"))
    if s.empty or len(s) < 13:
        return None, None
    yoy = (s.iloc[-1] / s.iloc[-13] - 1) * 100
    return float(yoy), s.index[-1]


# ============================================================
# Macro snapshot — convenience for the dashboard
# ============================================================
@dataclass
class FredMacroSnapshot:
    available: bool

    fed_funds:           Optional[float] = None
    fed_funds_target_lo: Optional[float] = None
    fed_funds_target_hi: Optional[float] = None

    yield_3m:  Optional[float] = None
    yield_2y:  Optional[float] = None
    yield_5y:  Optional[float] = None
    yield_10y: Optional[float] = None
    yield_30y: Optional[float] = None

    cpi_yoy_pct:      Optional[float] = None
    core_cpi_yoy_pct: Optional[float] = None
    pce_yoy_pct:      Optional[float] = None

    unemployment_pct:  Optional[float] = None
    sahm_rule:         Optional[float] = None
    sahm_triggered:    bool = False

    hy_spread_pct:     Optional[float] = None

    note: str = ""


def macro_snapshot() -> FredMacroSnapshot:
    """Latest readings for every series the macro page cares about."""
    if not _api_key():
        return FredMacroSnapshot(available=False, note="FRED_API_KEY not configured")

    def _last(sid: str) -> Optional[float]:
        v, _ = latest_value(sid)
        return v

    cpi_yoy, _ = inflation_yoy_pct("CPIAUCSL")
    core_yoy, _ = inflation_yoy_pct("CPILFESL")
    pce_yoy, _ = inflation_yoy_pct("PCEPI")
    sahm = _last("SAHMREALTIME")
    snap = FredMacroSnapshot(
        available=True,
        fed_funds=           _last("DFF"),
        fed_funds_target_lo= _last("DFEDTARL"),
        fed_funds_target_hi= _last("DFEDTARU"),

        yield_3m=  _last("DGS3MO"),
        yield_2y=  _last("DGS2"),
        yield_5y=  _last("DGS5"),
        yield_10y= _last("DGS10"),
        yield_30y= _last("DGS30"),

        cpi_yoy_pct=      cpi_yoy,
        core_cpi_yoy_pct= core_yoy,
        pce_yoy_pct=      pce_yoy,

        unemployment_pct=  _last("UNRATE"),
        sahm_rule=         sahm,
        sahm_triggered=    bool(sahm and sahm >= 0.5),

        hy_spread_pct=     _last("BAMLH0A0HYM2"),

        note=("Live readings from FRED. Inflation series are YoY % "
              "of the underlying index level."),
    )
    return snap


def is_available() -> bool:
    return bool(_api_key())
