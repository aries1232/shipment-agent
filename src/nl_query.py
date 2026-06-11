"""Natural-language query: question -> SQL -> grounded answer.

Two guards keep a non-engineer's question safe and truthful: `ensure_select` rejects
anything but a single read-only SELECT, and the final answer is summarised strictly from
the rows the query returned (no free-form recall).
"""

import json
import re

from src import storage
from src.config import settings
from src.gemini_client import get_client

SCHEMA_DESC = """Tables:
shipments(shipment_id, customer, sender, subject, status, outcome, reasoning, created_at)
  - one row per incoming shipment (an SU email with one or more documents).
  - created_at is ISO-8601 UTC text.
  - status: processing | stored | failed
  - outcome: auto_approve | human_review | amendment
  - a shipment is "pending review" / "flagged" when outcome IN ('human_review','amendment').
runs(run_id, shipment_id, doc_name, status, created_at, outcome, reasoning, amendment_request)
  - one row per document; shipment_id links a document to its shipment.
fields(run_id, field_name, value, confidence, source_snippet, validation_status, expected_value)
  - confidence is a 0..1 float.
  - validation_status: match | mismatch | uncertain"""

_FORBIDDEN = {
    "insert", "update", "delete", "drop", "alter", "create", "replace", "attach", "pragma",
}


def _clean_sql(text: str) -> str:
    return re.sub(r"```(?:sql)?", "", text).strip()


def ensure_select(sql: str) -> str:
    """Return the query if it is a single read-only SELECT, else raise ValueError."""
    s = _clean_sql(sql).rstrip(";").strip()
    if ";" in s:
        raise ValueError("multiple statements are not allowed")
    if not s.lower().startswith("select"):
        raise ValueError("only SELECT queries are allowed")
    bad = set(re.findall(r"[a-z_]+", s.lower())) & _FORBIDDEN
    if bad:
        raise ValueError(f"forbidden keyword(s): {', '.join(sorted(bad))}")
    return s


def _generate_sql(question: str) -> str:
    prompt = (
        f"{SCHEMA_DESC}\n\n"
        f"Write one SQLite SELECT query that answers this question:\n{question}\n\n"
        "Return only the SQL, no explanation, no markdown."
    )
    return get_client().generate_text(settings.text_model, prompt)


def _summarize(question: str, rows: list[dict]) -> str:
    prompt = (
        f"Question: {question}\n"
        f"Query result (JSON): {json.dumps(rows)}\n\n"
        "Answer the question in one sentence using only this result. "
        "If the result is empty, say there are no matching records."
    )
    return get_client().generate_text(settings.text_model, prompt)


def answer(question: str) -> dict:
    sql = ensure_select(_generate_sql(question))
    rows = storage.read_query(sql)
    return {"question": question, "sql": sql, "rows": rows, "answer": _summarize(question, rows)}
