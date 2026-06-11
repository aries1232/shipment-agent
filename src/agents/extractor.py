"""Extractor Agent: trade document (PDF/image) -> structured fields with confidence.

The prompt is the anti-hallucination boundary: the model may only report what is
visibly present, and must mark anything absent or illegible as null / confidence 0.
"""

from src.config import settings
from src.gemini_client import get_client
from src.schemas import ExtractedDocument

PROMPT = """You are a trade-document extraction agent. Extract the requested fields from the
attached document exactly as printed.

Rules:
- Only return a value you can actually see in the document.
- If a field is absent or not legible, set value to null and confidence to 0. Never guess.
- Copy values verbatim, keeping units, punctuation and casing.
- confidence (0.0-1.0) reflects how certain you are the value is correct and clearly legible.
- source_snippet: the short verbatim line or label+value where you read the field (for audit).

Fields:
- document_type: e.g. Commercial Invoice, Bill of Lading, Packing List, Certificate of Origin
- consignee_name, hs_code, port_of_loading, port_of_discharge, incoterms,
  description_of_goods, gross_weight, invoice_number, country_of_origin, shipper_name,
  invoice_date, total_value"""

_MIME_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def mime_for(filename: str) -> str:
    suffix = "." + filename.rsplit(".", 1)[-1].lower()
    if suffix not in _MIME_BY_SUFFIX:
        raise ValueError(f"Unsupported document type: {suffix}")
    return _MIME_BY_SUFFIX[suffix]


def extract(doc_bytes: bytes, mime_type: str) -> ExtractedDocument:
    result = get_client().extract(
        model=settings.extractor_model,
        prompt=PROMPT,
        doc_bytes=doc_bytes,
        mime_type=mime_type,
        schema=ExtractedDocument,
    )
    return result  # SDK parses the response into ExtractedDocument via response_schema
