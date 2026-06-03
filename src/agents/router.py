"""Router Agent: decides the outcome, then explains it.

The decision is a deterministic policy (auditable). The LLM is used only to write the
human-readable reasoning and amendment draft, and is grounded on facts computed in code
so it cannot invent a field or value.
"""

from src.config import settings
from src.gemini_client import get_client
from src.schemas import Decision, DecisionOutcome, ValidationReport


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
