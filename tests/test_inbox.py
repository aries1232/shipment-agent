import json

from src import inbox


def _seed(inbox_dir, shipment_id):
    d = inbox_dir / shipment_id
    d.mkdir(parents=True)
    (d / "_email.json").write_text(
        json.dumps({"shipment_id": shipment_id, "sender": "s", "customer": "c", "subject": "x"})
    )
    (d / "doc.pdf").write_bytes(b"%PDF-1.4 test")


def _use_temp_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(inbox, "INBOX", tmp_path / "inbox")
    monkeypatch.setattr(inbox, "PROCESSED", tmp_path / "processed")
    monkeypatch.setattr(inbox, "SENT", tmp_path / "sent")


def test_list_load_and_mark_processed(tmp_path, monkeypatch):
    _use_temp_dirs(tmp_path, monkeypatch)
    (tmp_path / "inbox").mkdir()
    _seed(tmp_path / "inbox", "SHP-1")

    assert inbox.list_new() == ["SHP-1"]

    email, attachments = inbox.load("SHP-1")
    assert email.shipment_id == "SHP-1"
    assert [name for name, _ in attachments] == ["doc.pdf"]  # _email.json excluded

    inbox.mark_processed("SHP-1")
    assert inbox.list_new() == []
    assert (tmp_path / "processed" / "SHP-1" / "doc.pdf").exists()


def test_peek_email_and_attachments_after_processing(tmp_path, monkeypatch):
    _use_temp_dirs(tmp_path, monkeypatch)
    (tmp_path / "inbox").mkdir()
    _seed(tmp_path / "inbox", "SHP-2")
    inbox.mark_processed("SHP-2")  # folder now lives under processed/

    assert inbox.peek_email("SHP-2").shipment_id == "SHP-2"
    assert [name for name, _ in inbox.attachments_of("SHP-2")] == ["doc.pdf"]


def test_list_sent_replies(tmp_path, monkeypatch):
    _use_temp_dirs(tmp_path, monkeypatch)

    inbox.mark_sent("SHP-3", "Approved, thank you.")

    replies = inbox.list_sent()
    assert len(replies) == 1
    assert replies[0].shipment_id == "SHP-3"
    assert replies[0].filename == "SHP-3_reply.txt"
    assert replies[0].body == "Approved, thank you."
    assert replies[0].sent_at
