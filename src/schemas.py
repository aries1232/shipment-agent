"""Typed contracts handed between agents. Confidence is first-class, never optional."""

from enum import Enum

from pydantic import BaseModel

# --- Extraction -------------------------------------------------------------

# The brief's required fields, document_type for context, plus common cross-doc trade fields.
EXTRACTION_FIELDS = (
    "document_type",
    "consignee_name",
    "hs_code",
    "port_of_loading",
    "port_of_discharge",
    "incoterms",
    "description_of_goods",
    "gross_weight",
    "invoice_number",
    "country_of_origin",
    "shipper_name",
    "invoice_date",
    "total_value",
)


class ExtractedField(BaseModel):
    value: str | None = None
    confidence: float = 0.0  # 0..1; 0 means "not present in the document"
    source_snippet: str | None = None  # verbatim text where the value was read


class ExtractedDocument(BaseModel):
    document_type: ExtractedField
    consignee_name: ExtractedField
    hs_code: ExtractedField
    port_of_loading: ExtractedField
    port_of_discharge: ExtractedField
    incoterms: ExtractedField
    description_of_goods: ExtractedField
    gross_weight: ExtractedField
    invoice_number: ExtractedField
    country_of_origin: ExtractedField
    shipper_name: ExtractedField
    invoice_date: ExtractedField
    total_value: ExtractedField

    def items(self) -> list[tuple[str, ExtractedField]]:
        return [(name, getattr(self, name)) for name in EXTRACTION_FIELDS]


# --- Validation -------------------------------------------------------------


class ValidationStatus(str, Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    UNCERTAIN = "uncertain"


class FieldValidation(BaseModel):
    field: str
    status: ValidationStatus
    found: str | None
    expected: str | None = None
    confidence: float
    note: str = ""


class ValidationReport(BaseModel):
    results: list[FieldValidation]

    @property
    def mismatches(self) -> list[FieldValidation]:
        return [r for r in self.results if r.status == ValidationStatus.MISMATCH]

    @property
    def uncertain(self) -> list[FieldValidation]:
        return [r for r in self.results if r.status == ValidationStatus.UNCERTAIN]


# --- Decision ---------------------------------------------------------------


class DecisionOutcome(str, Enum):
    AUTO_APPROVE = "auto_approve"
    HUMAN_REVIEW = "human_review"
    AMENDMENT = "amendment"


class Decision(BaseModel):
    outcome: DecisionOutcome
    reasoning: str
    amendment_request: str | None = None


# --- Pipeline run -----------------------------------------------------------


class RunStatus(str, Enum):
    EXTRACTED = "extracted"
    VALIDATED = "validated"
    STORED = "stored"
    FAILED = "failed"


class RunResult(BaseModel):
    run_id: str
    doc_name: str
    status: RunStatus
    extracted: ExtractedDocument | None = None
    report: ValidationReport | None = None
    decision: Decision | None = None


# --- Cross-document consistency (a shipment is many documents) ---------------


class ConsistencyStatus(str, Enum):
    AGREE = "agree"
    DISAGREE = "disagree"


class ConsistencyResult(BaseModel):
    field: str
    values_by_doc: dict[str, str]  # doc_name -> value, only docs that reported the field
    status: ConsistencyStatus


class StageTiming(BaseModel):
    name: str
    seconds: float


class ShipmentResult(BaseModel):
    shipment_id: str
    customer: str
    sender: str
    subject: str
    outcome: DecisionOutcome
    reasoning: str
    draft_reply: str
    docs: dict[str, ExtractedDocument]  # doc_name -> extraction
    reports: dict[str, ValidationReport]  # doc_name -> per-doc validation
    cross: list[ConsistencyResult]
    trace: list[StageTiming] = []  # per-stage timings, for pipeline transparency
