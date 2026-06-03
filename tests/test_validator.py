from src.agents.validator import validate
from src.schemas import ExtractedDocument, ValidationStatus

CLEAN = {
    "document_type": "Commercial Invoice",
    "consignee_name": "ACME Imports Ltd",
    "hs_code": "8471.30.00",
    "port_of_loading": "Shanghai, China",
    "port_of_discharge": "Rotterdam",
    "incoterms": "FOB",
    "description_of_goods": "Laptops",
    "gross_weight": "12,500 KG",
    "invoice_number": "INV-1",
}


def _doc(overrides: dict | None = None, conf: float = 0.95) -> ExtractedDocument:
    values = {**CLEAN, **(overrides or {})}
    return ExtractedDocument(**{k: {"value": v, "confidence": conf} for k, v in values.items()})


def _by_field(report):
    return {r.field: r for r in report.results}


def test_all_fields_match():
    report = validate(_doc())
    assert not report.mismatches and not report.uncertain
    assert all(r.status == ValidationStatus.MATCH for r in report.results)


def test_mismatch_reports_found_and_expected():
    r = _by_field(validate(_doc({"incoterms": "DDP Rotterdam"})))["incoterms"]
    assert r.status == ValidationStatus.MISMATCH
    assert r.found == "DDP Rotterdam"
    assert "FOB" in r.expected


def test_low_confidence_forces_uncertain():
    report = validate(_doc(conf=0.4))
    assert all(r.status == ValidationStatus.UNCERTAIN for r in report.results)


def test_missing_value_surfaces_as_uncertain():
    r = _by_field(validate(_doc({"invoice_number": None})))["invoice_number"]
    assert r.status == ValidationStatus.UNCERTAIN
    assert "not found" in r.note
