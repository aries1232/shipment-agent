from src.agents.router import _shipment_outcome
from src.schemas import (
    ConsistencyResult,
    ConsistencyStatus,
    DecisionOutcome,
    FieldValidation,
    ValidationReport,
    ValidationStatus,
)


def _report(*statuses: ValidationStatus) -> ValidationReport:
    return ValidationReport(
        results=[FieldValidation(field="f", status=s, found="x", confidence=0.9) for s in statuses]
    )


def _disagree() -> ConsistencyResult:
    return ConsistencyResult(
        field="consignee_name", values_by_doc={"a": "x", "b": "y"}, status=ConsistencyStatus.DISAGREE
    )


def test_clean_shipment_auto_approves():
    assert _shipment_outcome({"inv": _report(ValidationStatus.MATCH)}, []) == DecisionOutcome.AUTO_APPROVE


def test_cross_disagreement_requests_amendment():
    assert _shipment_outcome({"inv": _report(ValidationStatus.MATCH)}, [_disagree()]) == DecisionOutcome.AMENDMENT


def test_per_doc_mismatch_requests_amendment():
    assert _shipment_outcome({"inv": _report(ValidationStatus.MISMATCH)}, []) == DecisionOutcome.AMENDMENT


def test_uncertain_routes_to_human_review():
    assert _shipment_outcome({"inv": _report(ValidationStatus.UNCERTAIN)}, []) == DecisionOutcome.HUMAN_REVIEW


def test_mismatch_takes_priority_over_uncertain():
    reports = {"inv": _report(ValidationStatus.UNCERTAIN), "bol": _report(ValidationStatus.MISMATCH)}
    assert _shipment_outcome(reports, []) == DecisionOutcome.AMENDMENT
