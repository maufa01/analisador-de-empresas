"""
SQLite store for the user's watchlist + recently-analyzed history.

Two tables, same DB as ``user_assumptions_db`` (``~/.equity_app/assumptions.db``,
falling back to ``/tmp`` on locked-down hosts):

    watchlist(ticker TEXT PRIMARY KEY, added_at TEXT)
    recently_analyzed(ticker TEXT PRIMARY KEY, last_at TEXT)

Both tables ON CONFLICT REPLACE so the watchlist stays unique and the
recents always reflect the *latest* analysis time per ticker.
"""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Re-use the path-resolution logic that user_assumptions_db already vetted
from data.user_assumptions_db import db_path, IS_PERSISTENT  # noqa: F401


_SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist (
    ticker   TEXT PRIMARY KEY,
    added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recently_analyzed (
    ticker  TEXT PRIMARY KEY,
    last_at TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path()))
    conn.executescript(_SCHEMA)
    return conn


# ============================================================
# Watchlist
# ============================================================
def add_to_watchlist(ticker: str) -> None:
    if not ticker:
        return
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO watchlist (ticker, added_at) VALUES (?, ?) "
                "ON CONFLICT(ticker) DO NOTHING",
                (ticker.upper(), now),
            )
    except sqlite3.Error:
        pass


def remove_from_watchlist(ticker: str) -> None:
    if not ticker:
        return
    try:
        with _connect() as conn:
            conn.execute(
                "DELETE FROM watchlist WHERE ticker = ?", (ticker.upper(),),
            )
    except sqlite3.Error:
        pass


def list_watchlist() -> list[str]:
    """Return tickers in insertion order (oldest first)."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT ticker FROM watchlist ORDER BY added_at ASC"
            ).fetchall()
        return [r[0] for r in rows]
    except sqlite3.Error:
        return []


def is_in_watchlist(ticker: str) -> bool:
    if not ticker:
        return False
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM watchlist WHERE ticker = ?", (ticker.upper(),),
            ).fetchone()
        return row is not None
    except sqlite3.Error:
        return False


# ============================================================
# Recently analyzed
# ============================================================
def push_recent(ticker: str) -> None:
    """Bump (or insert) a ticker's last-analyzed timestamp to now."""
    if not ticker:
        return
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO recently_analyzed (ticker, last_at) VALUES (?, ?) "
                "ON CONFLICT(ticker) DO UPDATE SET last_at = excluded.last_at",
                (ticker.upper(), now),
            )
    except sqlite3.Error:
        pass


def list_recent(*, limit: int = 5) -> list[tuple[str, str]]:
    """Returns ``[(ticker, iso_timestamp)]`` newest first, capped at ``limit``."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT ticker, last_at FROM recently_analyzed "
                "ORDER BY last_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [(r[0], r[1]) for r in rows]
    except sqlite3.Error:
        return []


def clear_recent() -> None:
    try:
        with _connect() as conn:
            conn.execute("DELETE FROM recently_analyzed")
    except sqlite3.Error:
        pass
