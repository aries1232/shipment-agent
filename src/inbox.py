"""Simulated SU inbox — mocks the email plumbing so the pipeline has a real trigger.

Each incoming "email" is a folder under inbox/: an _email.json manifest plus the attached
PDFs. Processing moves the folder to processed/ (idempotent), and a sent reply is written
to sent/ — only ever by an explicit human action, never by the agent.
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "inbox"
PROCESSED = ROOT / "processed"
SENT = ROOT / "sent"
SAMPLES = ROOT / "samples" / "shipments"


class Email(BaseModel):
    shipment_id: str
    sender: str
    customer: str
    subject: str
    body: str = ""
    received_at: str = ""


class SentReply(BaseModel):
    shipment_id: str
    filename: str
    body: str
    sent_at: str


def _ensure_dirs() -> None:
    for d in (INBOX, PROCESSED, SENT):
        d.mkdir(parents=True, exist_ok=True)


def folder_of(shipment_id: str) -> Path:
    """Where a shipment's files live now: processed/ once handled, else still in inbox/."""
    processed = PROCESSED / shipment_id
    return processed if processed.exists() else INBOX / shipment_id


def peek_email(shipment_id: str) -> Email:
    folder = folder_of(shipment_id)
    return Email(**json.loads((folder / "_email.json").read_text(encoding="utf-8")))


def attachments_of(shipment_id: str) -> list[tuple[str, bytes]]:
    folder = folder_of(shipment_id)
    return [
        (p.name, p.read_bytes()) for p in sorted(folder.iterdir()) if not p.name.startswith("_")
    ]


def list_new() -> list[str]:
    _ensure_dirs()
    return sorted(p.name for p in INBOX.iterdir() if p.is_dir() and (p / "_email.json").exists())


def load(shipment_id: str) -> tuple[Email, list[tuple[str, bytes]]]:
    folder = INBOX / shipment_id
    email = Email(**json.loads((folder / "_email.json").read_text(encoding="utf-8")))
    attachments = [
        (p.name, p.read_bytes()) for p in sorted(folder.iterdir()) if not p.name.startswith("_")
    ]
    return email, attachments


def mark_processed(shipment_id: str) -> None:
    dest = PROCESSED / shipment_id
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(INBOX / shipment_id), str(dest))


def mark_sent(shipment_id: str, text: str) -> Path:
    _ensure_dirs()
    path = SENT / f"{shipment_id}_reply.txt"
    path.write_text(text, encoding="utf-8")
    return path


def list_sent() -> list[SentReply]:
    """Replies CG has sent back to suppliers, newest first."""
    _ensure_dirs()
    replies = []
    for path in SENT.glob("*_reply.txt"):
        shipment_id = path.name.removesuffix("_reply.txt")
        replies.append(
            SentReply(
                shipment_id=shipment_id,
                filename=path.name,
                body=path.read_text(encoding="utf-8"),
                sent_at=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            )
        )
    return sorted(replies, key=lambda r: r.sent_at, reverse=True)


def seed_sample(which: str) -> str:
    """Copy a prepared sample shipment into the inbox under a fresh id (the 'email arrives')."""
    _ensure_dirs()
    src = SAMPLES / which
    meta = json.loads((src / "_email.json").read_text(encoding="utf-8"))
    shipment_id = f"SHP-{uuid4().hex[:6].upper()}"
    dest = INBOX / shipment_id
    dest.mkdir(parents=True, exist_ok=True)
    for pdf in src.glob("*.pdf"):
        shutil.copy(pdf, dest / pdf.name)
    meta["shipment_id"] = shipment_id
    meta["received_at"] = datetime.now(timezone.utc).isoformat()
    (dest / "_email.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return shipment_id
