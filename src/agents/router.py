"""Router Agent: decides the outcome, then explains it.

The decision is a deterministic policy (auditable). The LLM is used only to write the
human-readable reasoning and amendment draft, and is grounded on facts computed in code
so it cannot invent a field or value.
"""

from src.config import settings
from src.gemini_client import get_client
from src.schemas import (
    ConsistencyResult,
    ConsistencyStatus,
    Decision,
    DecisionOutcome,
    ValidationReport,
)


def _outcome(report: ValidationReport) -> DecisionOutcome:
    if report.mismatches:
        return DecisionOutcome.AMENDMENT
    if report.uncertain:
        return DecisionOutcome.HUMAN_REVIEW
    return DecisionOutcome.AUTO_APPROVE


def _facts(report: ValidationReport) -> str:
    head = (
        f"{len(report.results)} fields checked, "
        f"{len(report.mismatches)} mismatch, {len(report.uncertain)} uncertain."
    )
    rows = [
        f"- {r.field}: found '{r.found}', expected '{r.expected}' ({r.status.value}; {r.note})"
        for r in report.mismatches + report.uncertain
    ]
    return "\n".join([head, *rows])


def _explain(outcome: DecisionOutcome, report: ValidationReport) -> str:
    prompt = (
        "A trade document was validated against customer ACME Imports Ltd's rules.\n"
        f"Decision: {outcome.value}.\n"
        f"Facts:\n{_facts(report)}\n\n"
        "In 2-3 sentences, explain to an operations reviewer why this decision was reached. "
        "Reference only the facts above. Do not invent fields or values."
    )
    return get_client().generate_text(settings.text_model, prompt)


def _draft_amendment(report: ValidationReport) -> str:
    discrepancies = "\n".join(
        f"- {r.field}: found '{r.found}', expected '{r.expected}'" for r in report.mismatches
    )
    prompt = (
        "Draft a short, professional amendment request email to the supplier asking them to "
        "correct the following discrepancies on the commercial invoice. Reference only these "
        "items; do not add new ones. Keep it under 120 words.\n\n"
        f"Discrepancies:\n{discrepancies}"
    )
    return get_client().generate_text(settings.text_model, prompt)


def decide(report: ValidationReport) -> Decision:
    outcome = _outcome(report)
    reasoning = _explain(outcome, report)
    amendment = _draft_amendment(report) if outcome == DecisionOutcome.AMENDMENT else None
    return Decision(outcome=outcome, reasoning=reasoning, amendment_request=amendment)


# --- Shipment-level: combine per-doc rules with cross-document consistency ----


def _shipment_outcome(
    reports: dict[str, ValidationReport], cross: list[ConsistencyResult]
) -> DecisionOutcome:
    disagree = any(c.status == ConsistencyStatus.DISAGREE for c in cross)
    if disagree or any(r.mismatches for r in reports.values()):
        return DecisionOutcome.AMENDMENT
    if any(r.uncertain for r in reports.values()):
        return DecisionOutcome.HUMAN_REVIEW
    return DecisionOutcome.AUTO_APPROVE


def _shipment_facts(
    reports: dict[str, ValidationReport], cross: list[ConsistencyResult]
) -> str:
    lines: list[str] = []
    for doc_name, report in reports.items():
        issues = report.mismatches + report.uncertain
        if issues:
            lines.append(f"{doc_name}:")
            lines += [
                f"  - {r.field}: found '{r.found}', expected '{r.expected}' ({r.status.value})"
                for r in issues
            ]
    for c in cross:
        if c.status == ConsistencyStatus.DISAGREE:
            vals = "; ".join(f"{n}='{v}'" for n, v in c.values_by_doc.items())
            lines.append(f"cross-document {c.field} disagrees across docs: {vals}")
    return "\n".join(lines) if lines else "All documents pass every rule and agree with each other."


def _explain_shipment(outcome: DecisionOutcome, facts: str, customer: str) -> str:
    prompt = (
        f"A shipment's documents were validated against customer {customer}'s rules and "
        "cross-checked against each other.\n"
        f"Decision: {outcome.value}.\n"
        f"Facts:\n{facts}\n\n"
        "In 2-3 sentences, explain to a CG reviewer why this decision was reached. "
        "Reference only the facts above. Do not invent fields or values."
    )
    return get_client().generate_text(settings.text_model, prompt)


def _draft_reply(outcome: DecisionOutcome, facts: str, customer: str) -> str:
    if outcome == DecisionOutcome.AUTO_APPROVE:
        instruction = (
            "Draft a short, professional email to the supplier confirming the shipment documents "
            f"for {customer} passed validation and are approved. Keep it under 90 words."
        )
    else:
        instruction = (
            "Draft a short, professional amendment-request email to the supplier listing every "
            "discrepancy below that must be corrected and resubmitted. Group by document, reference "
            "only these items, do not add new ones. Keep it under 160 words."
        )
    prompt = f"{instruction}\n\nFindings:\n{facts}"
    return get_client().generate_text(settings.text_model, prompt)


def decide_shipment(
    reports: dict[str, ValidationReport], cross: list[ConsistencyResult], customer: str
) -> tuple[DecisionOutcome, str, str]:
    """Return (outcome, CG-facing reasoning, draft reply email to the supplier)."""
    outcome = _shipment_outcome(reports, cross)
    facts = _shipment_facts(reports, cross)
    return outcome, _explain_shipment(outcome, facts, customer), _draft_reply(outcome, facts, customer)
