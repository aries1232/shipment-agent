"""Cross-document validator: shared fields must agree across a shipment's documents.

Per-doc validation (validator.py) checks each document against the customer's rules. This
deterministic step catches the other failure: a consignee or HS code that is individually
plausible on each doc but inconsistent between them — a classic cause of customs holds.
"""

from src.agents.validator import _norm
from src.schemas import ConsistencyResult, ConsistencyStatus, ExtractedDocument

CONSISTENCY_FIELDS = (
    "consignee_name",
    "hs_code",
    "description_of_goods",
    "country_of_origin",
)


def cross_check(docs: dict[str, ExtractedDocument]) -> list[ConsistencyResult]:
    results: list[ConsistencyResult] = []
    for field in CONSISTENCY_FIELDS:
        values = {name: getattr(doc, field).value for name, doc in docs.items()}
        present = {name: v for name, v in values.items() if v}
        if len(present) < 2:  # nothing to compare against
            continue
        agree = len({_norm(v) for v in present.values()}) == 1
        results.append(
            ConsistencyResult(
                field=field,
                values_by_doc=present,
                status=ConsistencyStatus.AGREE if agree else ConsistencyStatus.DISAGREE,
            )
        )
    return results
