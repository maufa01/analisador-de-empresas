"""
Alerts + per-ticker watchlist metadata (target / stop / notes / tags /
last score) in the same SQLite DB as ``watchlist_db``.

We deliberately keep this separate from ``watchlist_db.py`` so the
existing 2-table schema (and every page that reads it) remains
untouched. Joining to ``watchlist`` happens in queries via ticker.

Three new tables:
    watchlist_meta(ticker PK, target_price, stop_loss, notes, tags_json,
                   last_score, last_rating, last_checked_at)
    alert_config(id PK auto, ticker, kind, threshold, active, created_at)
    alert_event(id PK auto, ticker, kind, message, triggered_at,
                acknowledged, snapshot_json)

All queries swallow sqlite errors and return safe defaults — Streamlit
Cloud sometimes lands on read-only filesystems.
"""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from data.user_assumptions_db import db_path


_SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist_meta (
    ticker            TEXT PRIMARY KEY,
    target_price      REAL,
    stop_loss         REAL,
    notes             TEXT,
    tags_json         TEXT,
    last_score        INTEGER,
    last_rating       TEXT,
    last_checked_at   TEXT
);

CREATE TABLE IF NOT EXISTS alert_config (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    threshold   REAL,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_event (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    kind            TEXT NOT NULL,
    message         TEXT NOT NULL,
    triggered_at    TEXT NOT NULL,
    acknowledged    INTEGER NOT NULL DEFAULT 0,
    snapshot_json   TEXT
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path()))
    conn.executescript(_SCHEMA)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ============================================================
# Watchlist metadata
# ============================================================
def upsert_meta(
    ticker: str, *,
    target_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    notes: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> None:
    if not ticker:
        return
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO watchlist_meta
                    (ticker, target_price, stop_loss, notes, tags_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    target_price = COALESCE(excluded.target_price, watchlist_meta.target_price),
                    stop_loss    = COALESCE(excluded.stop_loss, watchlist_meta.stop_loss),
                    notes        = COALESCE(excluded.notes, watchlist_meta.notes),
                    tags_json    = COALESCE(excluded.tags_json, watchlist_meta.tags_json)
                """,
                (
                    ticker.upper(),
                    target_price,
                    stop_loss,
                    notes,
                    json.dumps(tags) if tags is not None else None,
                ),
            )
    except sqlite3.Error:
        pass


def get_meta(ticker: str) -> dict:
    if not ticker:
        return {}
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT target_price, stop_loss, notes, tags_json, "
                "last_score, last_rating, last_checked_at "
                "FROM watchlist_meta WHERE ticker = ?",
                (ticker.upper(),),
            ).fetchone()
    except sqlite3.Error:
        return {}

    if not row:
        return {}
    target_price, stop_loss, notes, tags_json, last_score, last_rating, last_at = row
    return {
        "ticker": ticker.upper(),
        "target_price": target_price,
        "stop_loss": stop_loss,
        "notes": notes or "",
        "tags": json.loads(tags_json) if tags_json else [],
        "last_score": last_score,
        "last_rating": last_rating,
        "last_checked_at": last_at,
    }


def update_last_check(ticker: str, *, score: Optional[int],
                      rating: Optional[str]) -> None:
    if not ticker:
        return
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO watchlist_meta (ticker, last_score, last_rating, last_checked_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    last_score      = excluded.last_score,
                    last_rating     = excluded.last_rating,
                    last_checked_at = excluded.last_checked_at
                """,
                (ticker.upper(), score, rating, _now()),
            )
    except sqlite3.Error:
        pass


def remove_meta(ticker: str) -> None:
    """Called when the user removes a ticker from the watchlist."""
    if not ticker:
        return
    try:
        with _connect() as conn:
            conn.execute("DELETE FROM watchlist_meta WHERE ticker = ?",
                         (ticker.upper(),))
            conn.execute("DELETE FROM alert_config WHERE ticker = ?",
                         (ticker.upper(),))
    except sqlite3.Error:
        pass


# ============================================================
# Alert config
# ============================================================
ALERT_KINDS = {
    "target_hit":     "Price hit target",
    "stop_loss":      "Price hit stop loss",
    "score_change":   "Score moved ≥15 points",
    "earnings_near":  "Earnings within N days",
    "sentiment_drop": "Sentiment dropped sharply",
}


def add_alert(ticker: str, kind: str, threshold: Optional[float] = None) -> None:
    if not ticker or kind not in ALERT_KINDS:
        return
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO alert_config (ticker, kind, threshold, active, created_at) "
                "VALUES (?, ?, ?, 1, ?)",
                (ticker.upper(), kind, threshold, _now()),
            )
    except sqlite3.Error:
        pass


def list_alerts(ticker: Optional[str] = None) -> pd.DataFrame:
    try:
        with _connect() as conn:
            if ticker:
                df = pd.read_sql(
                    "SELECT * FROM alert_config WHERE ticker = ? ORDER BY id DESC",
                    conn, params=(ticker.upper(),),
                )
            else:
                df = pd.read_sql(
                    "SELECT * FROM alert_config WHERE active = 1 ORDER BY ticker, id",
                    conn,
                )
        return df
    except sqlite3.Error:
        return pd.DataFrame()


def disable_alert(alert_id: int) -> None:
    try:
        with _connect() as conn:
            conn.execute(
                "UPDATE alert_config SET active = 0 WHERE id = ?", (int(alert_id),),
            )
    except sqlite3.Error:
        pass


# ============================================================
# Alert events (triggered)
# ============================================================
def record_event(ticker: str, kind: str, message: str,
                 snapshot: Optional[dict] = None) -> None:
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO alert_event "
                "(ticker, kind, message, triggered_at, acknowledged, snapshot_json) "
                "VALUES (?, ?, ?, ?, 0, ?)",
                (ticker.upper(), kind, message, _now(),
                 json.dumps(snapshot) if snapshot else None),
            )
    except sqlite3.Error:
        pass


def list_events(*, only_unack: bool = False, limit: int = 50) -> pd.DataFrame:
    try:
        with _connect() as conn:
            sql = "SELECT * FROM alert_event"
            if only_unack:
                sql += " WHERE acknowledged = 0"
            sql += " ORDER BY triggered_at DESC LIMIT ?"
            df = pd.read_sql(sql, conn, params=(int(limit),))
        return df
    except sqlite3.Error:
        return pd.DataFrame()


def acknowledge_event(event_id: int) -> None:
    try:
        with _connect() as conn:
            conn.execute(
                "UPDATE alert_event SET acknowledged = 1 WHERE id = ?",
                (int(event_id),),
            )
    except sqlite3.Error:
        pass


def acknowledge_all_events() -> None:
    try:
        with _connect() as conn:
            conn.execute("UPDATE alert_event SET acknowledged = 1 "
                         "WHERE acknowledged = 0")
    except sqlite3.Error:
        pass
