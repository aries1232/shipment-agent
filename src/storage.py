"""SQLite persistence — the single boundary the rest of the app talks to.

State is written after each pipeline step so a crash leaves a run at its last good
status (EXTRACTED / VALIDATED) for inspection or resume. Natural-language queries go
through a read-only connection, so generated SQL can never mutate data.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from src.config import settings
from src.schemas import Decision, ExtractedDocument, RunStatus, ShipmentResult, ValidationReport

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id            TEXT PRIMARY KEY,
    shipment_id       TEXT,
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
    source_snippet    TEXT,
    validation_status TEXT,
    expected_value    TEXT,
    PRIMARY KEY (run_id, field_name)
);
CREATE TABLE IF NOT EXISTS shipments (
    shipment_id        TEXT PRIMARY KEY,
    customer           TEXT,
    sender             TEXT,
    subject            TEXT,
    status             TEXT NOT NULL,
    outcome            TEXT,
    reasoning          TEXT,
    created_at         TEXT NOT NULL,
    processing_seconds REAL,
    doc_count          INTEGER
);
CREATE TABLE IF NOT EXISTS shipment_results (
    shipment_id TEXT PRIMARY KEY,
    result_json TEXT NOT NULL
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


def save_extraction(
    run_id: str, doc_name: str, doc: ExtractedDocument, shipment_id: str | None = None
) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO runs (run_id, shipment_id, doc_name, status, created_at) "
            "VALUES (?,?,?,?,?)",
            (run_id, shipment_id, doc_name, RunStatus.EXTRACTED.value, _now()),
        )
        for name, field in doc.items():
            c.execute(
                "INSERT OR REPLACE INTO fields (run_id, field_name, value, confidence, "
                "source_snippet) VALUES (?,?,?,?,?)",
                (run_id, name, field.value, field.confidence, field.source_snippet),
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


def save_shipment_start(
    shipment_id: str, customer: str, sender: str, subject: str, doc_count: int
) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO shipments "
            "(shipment_id, customer, sender, subject, status, created_at, doc_count) "
            "VALUES (?,?,?,?,?,?,?)",
            (shipment_id, customer, sender, subject, "processing", _now(), doc_count),
        )


def save_shipment_result(result: ShipmentResult) -> None:
    seconds = sum(t.seconds for t in result.trace)
    with _conn() as c:
        c.execute(
            "UPDATE shipments SET status=?, outcome=?, reasoning=?, processing_seconds=? "
            "WHERE shipment_id=?",
            (RunStatus.STORED.value, result.outcome.value, result.reasoning, seconds, result.shipment_id),
        )
        c.execute(
            "INSERT OR REPLACE INTO shipment_results (shipment_id, result_json) VALUES (?,?)",
            (result.shipment_id, result.model_dump_json()),
        )


def mark_shipment_failed(shipment_id: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE shipments SET status=? WHERE shipment_id=?",
            (RunStatus.FAILED.value, shipment_id),
        )


def recent_shipments(limit: int = 50) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT shipment_id, customer, sender, subject, status, outcome, created_at, "
            "processing_seconds, doc_count FROM shipments ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_shipment(shipment_id: str) -> dict | None:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM shipments WHERE shipment_id=?", (shipment_id,)
        ).fetchone()
        return dict(row) if row else None


def load_shipment_result(shipment_id: str) -> ShipmentResult | None:
    with _conn() as c:
        row = c.execute(
            "SELECT result_json FROM shipment_results WHERE shipment_id=?", (shipment_id,)
        ).fetchone()
    return ShipmentResult.model_validate_json(row["result_json"]) if row else None


def read_query(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a SELECT on a read-only connection. Used by the NL query layer."""
    conn = sqlite3.connect(f"file:{settings.db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()
