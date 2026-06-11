"""Shipment orchestrator: email -> per-doc extract+validate -> cross-check -> decide+draft.

Reuses Part 1's agents unchanged. State is persisted per step so a crash leaves the shipment
at its last good status; processing is idempotent per shipment_id. The agent only drafts a
reply — it never sends.
"""

import time
import uuid
from collections.abc import Callable

from src import inbox, storage
from src.agents import cross_validator, extractor, router, validator
from src.inbox import Email
from src.schemas import ShipmentResult, StageTiming

MAX_ATTACHMENTS = 8
MAX_BYTES = 10 * 1024 * 1024

OnEvent = Callable[[str], None] | None


def _validate_inputs(attachments: list[tuple[str, bytes]]) -> None:
    if not attachments:
        raise ValueError("shipment has no attachments")
    if len(attachments) > MAX_ATTACHMENTS:
        raise ValueError(f"too many attachments ({len(attachments)} > {MAX_ATTACHMENTS})")
    for name, data in attachments:
        extractor.mime_for(name)  # whitelist by type; raises on anything unsupported
        if len(data) > MAX_BYTES:
            raise ValueError(f"{name} exceeds the {MAX_BYTES}-byte limit")


def run_shipment(
    email: Email, attachments: list[tuple[str, bytes]], on_event: OnEvent = None
) -> ShipmentResult:
    _validate_inputs(attachments)
    storage.save_shipment_start(
        email.shipment_id, email.customer, email.sender, email.subject, len(attachments)
    )
    trace: list[StageTiming] = []

    def stage(label: str, fn):
        if on_event:
            on_event(label)
        start = time.perf_counter()
        out = fn()
        trace.append(StageTiming(name=label, seconds=time.perf_counter() - start))
        return out

    try:
        if on_event:
            on_event(f"Email received: {email.subject!r} - {len(attachments)} document(s)")
        rules = validator.load_rules(validator.rule_path_for(email.customer))
        docs, reports = {}, {}
        for i, (name, data) in enumerate(attachments, 1):
            run_id = uuid.uuid4().hex[:12]
            extracted = stage(
                f"Extracting {name} ({i}/{len(attachments)})",
                lambda data=data, name=name: extractor.extract(data, extractor.mime_for(name)),
            )
            storage.save_extraction(run_id, name, extracted, email.shipment_id)
            report = validator.validate(extracted, rules, flag_missing=False)
            storage.save_validation(run_id, report)
            docs[name], reports[name] = extracted, report

        missing = validator.completeness_report(docs, rules)
        if missing.results:  # a rule field absent from every document
            reports["required fields"] = missing
        cross = stage(
            f"Cross-checking {len(docs)} documents", lambda: cross_validator.cross_check(docs)
        )
        outcome, reasoning, draft = stage(
            "Deciding & drafting reply", lambda: router.decide_shipment(reports, cross, email.customer)
        )

        result = ShipmentResult(
            shipment_id=email.shipment_id,
            customer=email.customer,
            sender=email.sender,
            subject=email.subject,
            outcome=outcome,
            reasoning=reasoning,
            draft_reply=draft,
            docs=docs,
            reports=reports,
            cross=cross,
            trace=trace,
        )
        storage.save_shipment_result(result)
        if on_event:
            on_event(f"Decision: {outcome.value}")
        return result
    except Exception:
        storage.mark_shipment_failed(email.shipment_id)
        raise


def process_inbox(on_event: OnEvent = None) -> list[ShipmentResult]:
    """Drain the inbox. A failing shipment is recorded (status failed) and skipped — one bad
    email never strands its siblings or crashes the drain."""
    results: list[ShipmentResult] = []
    for shipment_id in inbox.list_new():
        try:
            email, attachments = inbox.load(shipment_id)
            results.append(run_shipment(email, attachments, on_event))
        except Exception as e:
            if on_event:
                on_event(f"{shipment_id} failed: {e}")
        finally:
            inbox.mark_processed(shipment_id)
    return results
