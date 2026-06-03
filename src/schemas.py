"""Typed contracts handed between agents. Confidence is first-class, never optional."""

from enum import Enum

from pydantic import BaseModel

# --- Extraction -------------------------------------------------------------

# The eight fields the brief requires, plus document_type for routing context.
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
)


class ExtractedField(BaseModel):
    value: str | None = None
    confidence: float = 0.0  # 0..1; 0 means "not present in the document"


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
