from src.agents.cross_validator import cross_check
from src.schemas import EXTRACTION_FIELDS, ConsistencyStatus, ExtractedDocument


def _doc(**overrides) -> ExtractedDocument:
    fields = {f: {"value": None, "confidence": 0.0} for f in EXTRACTION_FIELDS}
    for k, v in overrides.items():
        fields[k] = {"value": v, "confidence": 0.95}
    return ExtractedDocument(**fields)


def _by_field(docs):
    return {r.field: r for r in cross_check(docs)}


def test_consistent_fields_agree():
    docs = {
        "invoice": _doc(consignee_name="ACME Imports Ltd", hs_code="8471.30.00"),
        "bol": _doc(consignee_name="ACME Imports Ltd", hs_code="8471.30.00"),
    }
    res = _by_field(docs)
    assert res["consignee_name"].status == ConsistencyStatus.AGREE
    assert res["hs_code"].status == ConsistencyStatus.AGREE


def test_divergent_consignee_and_hs_disagree():
    docs = {
        "invoice": _doc(consignee_name="ACME Imports Ltd", hs_code="8471.30.00"),
        "bol": _doc(consignee_name="ACME Trading LLC", hs_code="8471.30.00"),
        "packing": _doc(consignee_name="ACME Imports Ltd", hs_code="8528.72.00"),
    }
    res = _by_field(docs)
    assert res["consignee_name"].status == ConsistencyStatus.DISAGREE
    assert res["hs_code"].status == ConsistencyStatus.DISAGREE


def test_field_reported_by_one_doc_is_not_compared():
    docs = {"invoice": _doc(country_of_origin="China"), "bol": _doc()}
    assert "country_of_origin" not in _by_field(docs)
