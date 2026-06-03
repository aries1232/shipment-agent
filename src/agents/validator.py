"""Validator Agent: deterministic rules engine. No LLM — comparison must be reproducible.

Two safety gates run before any rule: a missing value or a low-confidence extraction is
forced to `uncertain`, so a shaky field can never be silently approved.
"""

import difflib
import re
from functools import lru_cache
from pathlib import Path

import yaml

from src.config import settings
from src.schemas import ExtractedDocument, FieldValidation, ValidationReport, ValidationStatus

MATCH, MISMATCH, UNCERTAIN = (
    ValidationStatus.MATCH,
    ValidationStatus.MISMATCH,
    ValidationStatus.UNCERTAIN,
)


@lru_cache
def load_rules(path: str | None = None) -> dict:
    return yaml.safe_load(Path(path or settings.rules_path).read_text(encoding="utf-8"))


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def _expected_display(rule: str, expected) -> str | None:
    if rule == "allowed":
        return ", ".join(expected)
    if rule == "regex":
        return f"pattern {expected}"
    if rule == "unit":
        return f"unit {expected}"
    if rule == "present":
        return "non-empty value"
    return expected  # equals


def _check(rule: str, expected, value: str) -> tuple[ValidationStatus, str]:
    if rule == "equals":
        ratio = difflib.SequenceMatcher(None, _norm(value), _norm(expected)).ratio()
        note = f"name similarity {ratio:.0%}"
        if ratio >= 0.9:
            return MATCH, note
        if ratio >= 0.7:
            return UNCERTAIN, note + " — verify entity"
        return MISMATCH, note
    if rule == "allowed":
        ok = any(e.lower() in value.lower() for e in expected)
        return (MATCH, "") if ok else (MISMATCH, "not in approved list")
    if rule == "regex":
        ok = re.search(expected, value.strip()) is not None
        return (MATCH, "") if ok else (MISMATCH, "format does not match required pattern")
    if rule == "unit":
        ok = expected.lower() in value.lower()
        return (MATCH, "") if ok else (MISMATCH, f"expected unit {expected}")
    if rule == "present":
        return MATCH, ""
    raise ValueError(f"unknown rule: {rule}")


def validate(doc: ExtractedDocument, rules: dict | None = None) -> ValidationReport:
    field_rules = (rules or load_rules())["fields"]
    results: list[FieldValidation] = []

    for name, field in doc.items():
        spec = field_rules.get(name)
        if spec is None:  # no rule for this field (e.g. document_type) — context only
            continue

        expected = _expected_display(spec["rule"], spec.get("expected"))
        value, confidence = field.value, field.confidence

        if not value:
            status, note = UNCERTAIN, "not found in document"
        elif confidence < settings.confidence_threshold:
            status, note = UNCERTAIN, f"low extraction confidence ({confidence:.0%})"
        else:
            status, note = _check(spec["rule"], spec.get("expected"), value)

        results.append(
            FieldValidation(
                field=name,
                status=status,
                found=value,
                expected=expected,
                confidence=confidence,
                note=note,
            )
        )

    return ValidationReport(results=results)
