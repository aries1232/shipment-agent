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


def rule_path_for(customer: str) -> str:
    """Map a customer name to its rule set; fall back to the default if none exists."""
    slug = re.sub(r"[^a-z0-9]+", "_", customer.lower()).strip("_")
    candidate = Path("rules") / f"{slug}.yaml"
    return str(candidate) if candidate.exists() else settings.rules_path


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


def validate(
    doc: ExtractedDocument, rules: dict | None = None, flag_missing: bool = True
) -> ValidationReport:
    """Validate one document. With flag_missing=False, a field absent from this document is
    skipped rather than flagged — used per-doc in a shipment, where another document may carry
    it and shipment-level completeness covers anything missing everywhere."""
    field_rules = (rules or load_rules())["fields"]
    results: list[FieldValidation] = []

    for name, field in doc.items():
        spec = field_rules.get(name)
        if spec is None:  # no rule for this field (e.g. document_type) — context only
            continue

        expected = _expected_display(spec["rule"], spec.get("expected"))
        value, confidence = field.value, field.confidence

        if not value:
            if not flag_missing:
                continue
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


def completeness_report(
    docs: dict[str, ExtractedDocument], rules: dict | None = None
) -> ValidationReport:
    """Flag rule fields that are absent from every document in the shipment (no silent gaps)."""
    field_rules = (rules or load_rules())["fields"]
    results = [
        FieldValidation(
            field=name,
            status=UNCERTAIN,
            found=None,
            expected=_expected_display(spec["rule"], spec.get("expected")),
            confidence=0.0,
            note="required field not present in any document",
        )
        for name, spec in field_rules.items()
        if all(not getattr(doc, name).value for doc in docs.values())
    ]
    return ValidationReport(results=results)
