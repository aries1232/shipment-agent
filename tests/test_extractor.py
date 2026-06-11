from pathlib import Path

from src.agents import extractor
from src.schemas import EXTRACTION_FIELDS, ExtractedDocument

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "commercial_invoice_clean.pdf"

FAKE_FIELDS = {
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


class _FakeClient:
    def extract(self, model, prompt, doc_bytes, mime_type, schema):
        assert mime_type == "application/pdf"  # mime detection wired correctly
        assert doc_bytes  # the sample bytes reached the client
        fields = {f: {"value": None, "confidence": 0.0} for f in EXTRACTION_FIELDS}
        fields.update({k: {"value": v, "confidence": 0.95} for k, v in FAKE_FIELDS.items()})
        return ExtractedDocument(**fields)


def test_mime_for_pdf():
    assert extractor.mime_for("commercial_invoice_clean.pdf") == "application/pdf"


def test_extract_returns_structured_document(monkeypatch):
    monkeypatch.setattr(extractor, "get_client", lambda: _FakeClient())
    doc = extractor.extract(SAMPLE.read_bytes(), extractor.mime_for(SAMPLE.name))
    assert isinstance(doc, ExtractedDocument)
    assert doc.consignee_name.value == "ACME Imports Ltd"
    assert doc.invoice_number.confidence == 0.95
