"""
SQLite store for per-ticker custom assumptions.

Schema:
    user_assumptions(
        ticker     TEXT PRIMARY KEY,
        params     TEXT NOT NULL,        -- JSON-encoded Assumptions.to_dict()
        updated_at TEXT NOT NULL         -- ISO-8601 UTC
    )

The DB lives at ``~/.equity_app/assumptions.db`` by default. On
read-only filesystems (Streamlit Cloud's container has an ephemeral
``/mount/src`` and the home dir is read-only at deploy time for some
configs) we silently fall back to ``/tmp`` and warn via ``IS_PERSISTENT``
so the UI can show "session-scoped" rather than promise persistence.
"""
from __future__ import annotations
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ============================================================
# Path resolution
# ============================================================
def _candidate_dirs() -> list[Path]:
    """Try the user's home first; fall back to /tmp on locked-down hosts."""
    out: list[Path] = []
    home = os.environ.get("HOME") or os.path.expanduser("~")
    if home:
        out.append(Path(home) / ".equity_app")
    out.append(Path(tempfile.gettempdir()) / "equity_app")
    return out


def _resolve_db_path() -> tuple[Path, bool]:
    """
    Returns (db_path, is_persistent).

    is_persistent = False when we had to fall back to /tmp — the caller
    should warn the user that saved assumptions die with the container.
    """
    for d in _candidate_dirs():
        try:
            d.mkdir(parents=True, exist_ok=True)
            test = d / ".write_test"
            test.write_text("ok")
            test.unlink()
            return d / "assumptions.db", d == _candidate_dirs()[0]
        except (OSError, PermissionError):
            continue
    # Last resort — in-memory; never persists.
    return Path(":memory:"), False


_DB_PATH, IS_PERSISTENT = _resolve_db_path()


# ============================================================
# Schema bootstrap
# ============================================================
_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_assumptions (
    ticker     TEXT PRIMARY KEY,
    params     TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.executescript(_SCHEMA)
    return conn


# ============================================================
# Public API
# ============================================================
def save_assumptions(ticker: str, params: dict) -> None:
    """Upsert the assumptions for ``ticker``. Silent on errors."""
    if not ticker:
        return
    payload = json.dumps(params, default=float)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO user_assumptions (ticker, params, updated_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(ticker) DO UPDATE SET "
                "params = excluded.params, updated_at = excluded.updated_at",
                (ticker.upper(), payload, now),
            )
    except sqlite3.Error:
        # Persistence is best-effort — the panel keeps working from
        # session_state regardless.
        pass


def load_assumptions(ticker: str) -> Optional[dict]:
    """Return the saved params for ``ticker`` or None if absent / corrupt."""
    if not ticker:
        return None
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT params FROM user_assumptions WHERE ticker = ?",
                (ticker.upper(),),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])
    except (sqlite3.Error, json.JSONDecodeError):
        return None


def load_assumptions_with_meta(ticker: str) -> Optional[tuple[dict, str]]:
    """Like ``load_assumptions`` but also returns the ISO timestamp."""
    if not ticker:
        return None
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT params, updated_at FROM user_assumptions WHERE ticker = ?",
                (ticker.upper(),),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row[0]), str(row[1])
    except (sqlite3.Error, json.JSONDecodeError):
        return None


def delete_assumptions(ticker: str) -> None:
    """Drop the row for ``ticker``; no-op if absent."""
    if not ticker:
        return
    try:
        with _connect() as conn:
            conn.execute(
                "DELETE FROM user_assumptions WHERE ticker = ?",
                (ticker.upper(),),
            )
    except sqlite3.Error:
        pass


def db_path() -> Path:
    """Where the DB actually landed (handy for diagnostics)."""
    return _DB_PATH
