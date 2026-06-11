from src.agents.router import _outcome
from src.schemas import DecisionOutcome, FieldValidation, ValidationReport, ValidationStatus


def _field(status: ValidationStatus) -> FieldValidation:
    return FieldValidation(field="invoice_number", status=status, found="x", confidence=0.95)


def _report(*statuses: ValidationStatus) -> ValidationReport:
    return ValidationReport(results=[_field(s) for s in statuses])


def test_all_match_auto_approves():
    report = _report(ValidationStatus.MATCH, ValidationStatus.MATCH)
    assert _outcome(report) == DecisionOutcome.AUTO_APPROVE


def test_uncertain_routes_to_human_review():
    report = _report(ValidationStatus.MATCH, ValidationStatus.UNCERTAIN)
    assert _outcome(report) == DecisionOutcome.HUMAN_REVIEW


def test_mismatch_requests_amendment():
    report = _report(ValidationStatus.MATCH, ValidationStatus.MISMATCH)
    assert _outcome(report) == DecisionOutcome.AMENDMENT


def test_mismatch_takes_priority_over_uncertain():
    report = _report(ValidationStatus.UNCERTAIN, ValidationStatus.MISMATCH)
    assert _outcome(report) == DecisionOutcome.AMENDMENT
