"""Pipeline orchestrator: extract -> validate -> decide, persisting after each step.

State is committed between steps, so a crash leaves the run at its last good status
rather than vanishing. Writes are keyed by run_id and idempotent, so a run is safe to
re-process. On any failure the run is marked FAILED and the error is surfaced.
"""

import uuid

from src import storage
from src.agents import extractor, router, validator
from src.schemas import RunResult, RunStatus


def run_pipeline(doc_bytes: bytes, doc_name: str) -> RunResult:
    mime_type = extractor.mime_for(doc_name)
    run_id = uuid.uuid4().hex[:12]

    try:
        extracted = extractor.extract(doc_bytes, mime_type)
        storage.save_extraction(run_id, doc_name, extracted)

        report = validator.validate(extracted)
        storage.save_validation(run_id, report)

        decision = router.decide(report)
        storage.save_decision(run_id, decision)

        return RunResult(
            run_id=run_id,
            doc_name=doc_name,
            status=RunStatus.STORED,
            extracted=extracted,
            report=report,
            decision=decision,
        )
    except Exception:
        storage.mark_failed(run_id)
        raise
