"""SQLite persistence — the single boundary the rest of the app talks to.

State is written after each pipeline step so a crash leaves a run at its last good
status (EXTRACTED / VALIDATED) for inspection or resume. Natural-language queries go
through a read-only connection, so generated SQL can never mutate data.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from src.config import settings
from src.schemas import Decision, ExtractedDocument, RunStatus, ValidationReport

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id            TEXT PRIMARY KEY,
    doc_name          TEXT NOT NULL,
    status            TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    outcome           TEXT,
    reasoning         TEXT,
    amendment_request TEXT
);
CREATE TABLE IF NOT EXISTS fields (
    run_id            TEXT NOT NULL,
    field_name        TEXT NOT NULL,
    value             TEXT,
    confidence        REAL,
    validation_status TEXT,
    expected_value    TEXT,
    PRIMARY KEY (run_id, field_name)
);
"""


@contextmanager
def _conn():
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    with _conn() as c:
        c.executescript(SCHEMA)


def save_extraction(run_id: str, doc_name: str, doc: ExtractedDocument) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO runs (run_id, doc_name, status, created_at) VALUES (?,?,?,?)",
            (run_id, doc_name, RunStatus.EXTRACTED.value, _now()),
        )
        for name, field in doc.items():
            c.execute(
                "INSERT OR REPLACE INTO fields (run_id, field_name, value, confidence) "
                "VALUES (?,?,?,?)",
                (run_id, name, field.value, field.confidence),
            )


def save_validation(run_id: str, report: ValidationReport) -> None:
    with _conn() as c:
        for r in report.results:
            c.execute(
                "UPDATE fields SET validation_status=?, expected_value=? "
                "WHERE run_id=? AND field_name=?",
                (r.status.value, r.expected, run_id, r.field),
            )
        c.execute("UPDATE runs SET status=? WHERE run_id=?", (RunStatus.VALIDATED.value, run_id))


def save_decision(run_id: str, decision: Decision) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE runs SET status=?, outcome=?, reasoning=?, amendment_request=? WHERE run_id=?",
            (
                RunStatus.STORED.value,
                decision.outcome.value,
                decision.reasoning,
                decision.amendment_request,
                run_id,
            ),
        )


def mark_failed(run_id: str) -> None:
    with _conn() as c:
        c.execute("UPDATE runs SET status=? WHERE run_id=?", (RunStatus.FAILED.value, run_id))


def recent_runs(limit: int = 20) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT run_id, doc_name, status, outcome, created_at "
            "FROM runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def read_query(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a SELECT on a read-only connection. Used by the NL query layer."""
    conn = sqlite3.connect(f"file:{settings.db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()
