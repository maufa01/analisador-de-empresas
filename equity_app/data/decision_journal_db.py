"""
Decision journal — persistent record of buy / sell / hold / watch
decisions with the thesis behind each one.

The point isn't documentation theatre — it's so that, six months later
when the position is up 30% or down 20%, you can re-read what you
thought at decision time and see whether the thesis played out, the
thesis was wrong, or the thesis was right but mispriced.

Storage: SQLite under ``data/decisions.db``. One row per decision.
Closing a decision flips status and records the exit price + outcome
notes — the row itself is preserved so the history is intact.
"""
from __future__ import annotations
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional


Action = Literal["buy", "sell", "hold", "watch"]
Status = Literal["open", "closed", "cancelled"]


@dataclass
class Decision:
    id: int
    ticker: str
    action: Action
    decided_at: str                # ISO 8601 string
    price_at_decision: Optional[float]
    intrinsic_at_decision: Optional[float]
    conviction: Optional[int]      # 1-5
    thesis: str                    # why am I doing this?
    exit_criteria: str             # what would invalidate the thesis?
    status: Status
    closed_at: Optional[str] = None
    exit_price: Optional[float] = None
    outcome_notes: Optional[str] = None


# ============================================================
# Internals
# ============================================================
def _db_path() -> Path:
    p = Path("data/decisions.db")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS decisions (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker                TEXT NOT NULL,
            action                TEXT NOT NULL,
            decided_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            price_at_decision     REAL,
            intrinsic_at_decision REAL,
            conviction            INTEGER,
            thesis                TEXT NOT NULL DEFAULT '',
            exit_criteria         TEXT NOT NULL DEFAULT '',
            status                TEXT NOT NULL DEFAULT 'open',
            closed_at             TIMESTAMP,
            exit_price            REAL,
            outcome_notes         TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_dec_ticker ON decisions(ticker);
        CREATE INDEX IF NOT EXISTS ix_dec_status ON decisions(status);
        CREATE INDEX IF NOT EXISTS ix_dec_decided ON decisions(decided_at);
        """)


def _row_to_decision(row) -> Decision:
    return Decision(
        id=row["id"],
        ticker=row["ticker"],
        action=row["action"],
        decided_at=row["decided_at"],
        price_at_decision=row["price_at_decision"],
        intrinsic_at_decision=row["intrinsic_at_decision"],
        conviction=row["conviction"],
        thesis=row["thesis"] or "",
        exit_criteria=row["exit_criteria"] or "",
        status=row["status"],
        closed_at=row["closed_at"],
        exit_price=row["exit_price"],
        outcome_notes=row["outcome_notes"],
    )


# ============================================================
# Public API
# ============================================================
def add_decision(
    *,
    ticker: str,
    action: Action,
    thesis: str,
    exit_criteria: str = "",
    price_at_decision: Optional[float] = None,
    intrinsic_at_decision: Optional[float] = None,
    conviction: Optional[int] = None,
) -> int:
    """Record a new decision. Returns the new row id."""
    init_db()
    if action not in ("buy", "sell", "hold", "watch"):
        raise ValueError(f"Invalid action: {action!r}")
    if conviction is not None and not (1 <= int(conviction) <= 5):
        raise ValueError("conviction must be 1-5")
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO decisions (
                ticker, action, price_at_decision, intrinsic_at_decision,
                conviction, thesis, exit_criteria
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticker.upper(), action, price_at_decision,
                intrinsic_at_decision,
                int(conviction) if conviction is not None else None,
                thesis, exit_criteria,
            ),
        )
        return int(cur.lastrowid)


def list_decisions(
    *,
    ticker: Optional[str] = None,
    status: Optional[str] = None,        # "open" | "closed" | "cancelled" | "all"
    limit: int = 100,
) -> list[Decision]:
    """Most-recent-first listing. ``status='all'`` returns every row."""
    init_db()
    sql = "SELECT * FROM decisions WHERE 1=1"
    params: list = []
    if ticker:
        sql += " AND ticker = ?"
        params.append(ticker.upper())
    if status and status != "all":
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY decided_at DESC LIMIT ?"
    params.append(int(limit))
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_decision(r) for r in rows]


def get_decision(decision_id: int) -> Optional[Decision]:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM decisions WHERE id = ?", (int(decision_id),),
        ).fetchone()
    return _row_to_decision(row) if row else None


def close_decision(
    decision_id: int, *,
    exit_price: Optional[float] = None,
    outcome_notes: str = "",
    status: Status = "closed",
) -> bool:
    """Close (or cancel) an open decision. Returns True on success."""
    init_db()
    if status not in ("closed", "cancelled"):
        raise ValueError(f"Invalid close status: {status!r}")
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE decisions
            SET status = ?, closed_at = ?, exit_price = ?, outcome_notes = ?
            WHERE id = ?
            """,
            (
                status, datetime.utcnow().isoformat(timespec="seconds"),
                exit_price, outcome_notes, int(decision_id),
            ),
        )
        return cur.rowcount > 0


def delete_decision(decision_id: int) -> bool:
    """Hard-delete a decision (use sparingly — close is preferred)."""
    init_db()
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM decisions WHERE id = ?", (int(decision_id),),
        )
        return cur.rowcount > 0


def last_reviewed_per_ticker() -> dict[str, str]:
    """Return ``{ticker: most_recent_decided_at}`` across every decision.
    Used by the watchlist panel to show 'last reviewed' per ticker."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT ticker, MAX(decided_at) AS last_at FROM decisions "
            "GROUP BY ticker"
        ).fetchall()
    return {r["ticker"]: r["last_at"] for r in rows if r["last_at"]}
