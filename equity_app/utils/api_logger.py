"""
Session-scoped API request log.

Stores the last 200 API events in ``st.session_state`` so the
diagnostic panel can show what happened without burning extra
network. Producers (provider modules) call ``log_api_request`` after
each external request.

Each event:
    timestamp:        UTC datetime
    provider:         "finnhub" / "fred" / "sec" / …
    endpoint:         relative path or function name
    ticker:           optional
    success:          bool
    response_time_ms: int  (best-effort, may be None)
    cached:           bool
    error:            str (only when success=False)
    response_summary: str  (free-form, e.g. "200 OK 12 rows")
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Optional

_MAX_LOG_LENGTH = 200


def _events() -> list[dict]:
    try:
        import streamlit as st
    except ImportError:
        return []
    if "_api_request_log" not in st.session_state:
        st.session_state["_api_request_log"] = []
    return st.session_state["_api_request_log"]


def log_api_request(
    *,
    provider: str,
    endpoint: str,
    ticker: Optional[str] = None,
    success: bool = True,
    response_time_ms: Optional[int] = None,
    error: Optional[str] = None,
    cached: bool = False,
    response_summary: Optional[str] = None,
) -> None:
    """Append one event to the session-scoped log. Silent no-op outside
    a Streamlit runtime so non-UI callers (tests, batch scripts) can
    safely call providers without configuring anything."""
    try:
        import streamlit as st  # noqa: F401
    except ImportError:
        return
    log = _events()
    log.append({
        "timestamp":        datetime.now(timezone.utc),
        "provider":         provider,
        "endpoint":         endpoint,
        "ticker":           ticker,
        "success":          bool(success),
        "response_time_ms": response_time_ms,
        "cached":           bool(cached),
        "error":            error,
        "response_summary": response_summary,
    })
    if len(log) > _MAX_LOG_LENGTH:
        del log[: len(log) - _MAX_LOG_LENGTH]


def get_log() -> list[dict]:
    return list(_events())


def clear_log() -> None:
    try:
        import streamlit as st
    except ImportError:
        return
    st.session_state["_api_request_log"] = []
