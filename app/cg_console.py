"""CG console: a live operations screen. The console monitors the SU inbox; when an email
arrives it announces it, analyzes every attached document stage by stage (in full view), and
hands CG a verification result + an editable draft reply. The agent drafts; it never sends.
"""

import html
import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from src import inbox, nl_query, shipment, storage
from src.config import settings
from src.schemas import ConsistencyStatus, DecisionOutcome, ShipmentResult

OUTCOME_STYLE = {
    DecisionOutcome.AUTO_APPROVE: ("#16a34a", "#f0fdf4", "Auto-approved"),
    DecisionOutcome.HUMAN_REVIEW: ("#d97706", "#fffbeb", "Flagged for human review"),
    DecisionOutcome.AMENDMENT: ("#dc2626", "#fef2f2", "Amendment requested"),
}
ROW_TINT = {"match": "#f0fdf4", "mismatch": "#fef2f2", "uncertain": "#fffbeb"}
DISPLAY_TZ = timezone(timedelta(hours=5, minutes=30))
PREPARED = {
    "PO-4512 | ACME | 3 docs (clean)": "clean",
    "PO-4513 | ACME | 3 docs (issues)": "messy",
    "PO-7782 | Globex | 3 docs (issues)": "globex_messy",
}

st.set_page_config(page_title="CG Dashboard", page_icon="", layout="wide")
storage.init_db()

st.markdown(
    """
    <style>
      .block-container {padding-top:2.2rem;max-width:1240px;}
      .hero-title {display:block;margin:0 0 .55rem;padding:.25rem 0 .1rem;
        color:#4f46e5;font-size:2rem;font-weight:800;line-height:1.35;
        background:none;-webkit-text-fill-color:#4f46e5;overflow:visible;}
      .live {color:#16a34a;font-weight:700;font-size:.85rem;}
      .decision-card {padding:16px 20px;border-radius:14px;margin:4px 0 10px;}
      .decision-title {font-size:1.2rem;font-weight:700;margin-bottom:4px;}
      .decision-reason {color:#475569;font-size:.93rem;line-height:1.5;}
      .chip {display:inline-block;padding:2px 10px;border-radius:999px;font-size:.72rem;font-weight:700;}
      div[data-testid="stMetric"] {background:#f6f7fb;border:1px solid #eceef4;
        border-radius:12px;padding:10px 14px;}
    </style>
    """,
    unsafe_allow_html=True,
)


def _chip(label: str, color: str, bg: str) -> str:
    return f'<span class="chip" style="color:{color};background:{bg}">{label}</span>'


def _badge(status: str, outcome: str | None) -> str:
    if status == "failed":
        return _chip("Failed", "#dc2626", "#fef2f2")
    if status == "queued":
        return _chip("In CG inbox", "#2563eb", "#eff6ff")
    if status == "processing" or not outcome:
        return _chip("Processing", "#d97706", "#fffbeb")
    try:
        color, bg, label = OUTCOME_STYLE[DecisionOutcome(outcome)]
    except ValueError:
        return _chip(str(outcome).replace("_", " ").title(), "#475569", "#f8fafc")
    return _chip(label, color, bg)


def _row_value(row: dict, key: str, fallback: object = "") -> object:
    value = row.get(key)
    return fallback if value is None or value == "" else value


def _local_timestamp(value: object, *, include_date: bool = False) -> str:
    if not value:
        return ""
    raw = str(value)
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw[:16].replace("T", " ")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(DISPLAY_TZ)
    return local.strftime("%Y-%m-%d %H:%M UTC+05:30" if include_date else "%H:%M")


def _shipment_folder(shipment_id: str):
    if hasattr(inbox, "folder_of"):
        return inbox.folder_of(shipment_id)
    processed = inbox.PROCESSED / shipment_id
    return processed if processed.exists() else inbox.INBOX / shipment_id


def _email_body(shipment_id: str) -> str:
    if hasattr(inbox, "peek_email"):
        try:
            return inbox.peek_email(shipment_id).body
        except FileNotFoundError:
            return ""
    path = _shipment_folder(shipment_id) / "_email.json"
    if not path.exists():
        return ""
    return json.loads(path.read_text(encoding="utf-8")).get("body", "")


def _attachments(shipment_id: str) -> list[tuple[str, bytes]]:
    if hasattr(inbox, "attachments_of"):
        try:
            return inbox.attachments_of(shipment_id)
        except FileNotFoundError:
            return []
    folder = _shipment_folder(shipment_id)
    if not folder.exists():
        return []
    return [
        (p.name, p.read_bytes()) for p in sorted(folder.iterdir()) if not p.name.startswith("_")
    ]


def _preview(text: str, limit: int = 90) -> str:
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= limit else f"{one_line[: limit - 1]}..."


def _queued_shipments() -> list[dict]:
    queued = []
    for shipment_id in inbox.list_new():
        try:
            email = inbox.peek_email(shipment_id)
        except FileNotFoundError:
            continue
        queued.append(
            {
                "shipment_id": email.shipment_id,
                "customer": email.customer,
                "sender": email.sender,
                "subject": email.subject,
                "status": "queued",
                "outcome": None,
                "created_at": email.received_at,
                "processing_seconds": None,
                "doc_count": len(_attachments(shipment_id)),
            }
        )
    return queued


# --- Supplier (SU) outbox + monitor controls (sidebar) ----------------------

with st.sidebar:
    st.markdown("### Supplier (SU) — Outbox")
    st.caption("Supplier")
    choice = st.radio("Prepared shipments", list(PREPARED), label_visibility="collapsed")
    if st.button("Send to CG ▸", type="primary", use_container_width=True, disabled=not settings.gemini_api_key):
        st.session_state["selected"] = inbox.seed_sample(PREPARED[choice])
        st.toast("📨 Email sent to CG")
    st.divider()
    st.markdown("### Supplier (SU) — Inbox")
    replies = inbox.list_sent()
    if not replies:
        st.caption("No CG replies yet.")
    for reply in replies[:5]:
        sent_at = _local_timestamp(reply.sent_at, include_date=True)
        with st.expander(f"Reply for {reply.shipment_id}"):
            if sent_at:
                st.caption(f"Received {sent_at}")
            st.caption(_preview(reply.body))
            st.text_area(
                "Message",
                reply.body,
                height=160,
                key=f"sent_reply_{reply.filename}",
                disabled=True,
                label_visibility="collapsed",
            )
    st.divider()
    st.markdown('<span class="live">● Live monitoring</span> · auto-polling every 2s', unsafe_allow_html=True)

# --- Header + KPI strip -----------------------------------------------------

st.markdown('<div class="hero-title">CG Dashboard</div>', unsafe_allow_html=True)

queued_ships = _queued_shipments()
queued_ids = {str(s["shipment_id"]) for s in queued_ships}
queued_by_id = {str(s["shipment_id"]): s for s in queued_ships}
ships = queued_ships + [
    s for s in storage.recent_shipments() if str(s.get("shipment_id")) not in queued_ids
]
pending = sum(1 for s in ships if s.get("outcome") in ("human_review", "amendment"))
approved = sum(1 for s in ships if s.get("outcome") == "auto_approve")
amendments = sum(1 for s in ships if s.get("outcome") == "amendment")
times = [s.get("processing_seconds") for s in ships if s.get("processing_seconds")]
k1, k2, k3, k4 = st.columns(4)
k1.metric("Pending review", pending)
k2.metric("Auto-approved", approved)
k3.metric("Amendments", amendments)
k4.metric("Avg processing", f"{sum(times) / len(times):.1f}s" if times else "—") # type: ignore

if not settings.gemini_api_key:
    st.warning("GEMINI_API_KEY is not set. Add it to `.env` to process shipments.")


# --- Live monitor: detect new mail and analyze it in full view --------------

@st.fragment(run_every=2)
def monitor() -> None:
    new = inbox.list_new()
    now = datetime.now().strftime("%H:%M:%S")
    if new and settings.gemini_api_key:
        seen = set(st.session_state.get("seen_in_cg_inbox", []))
        first_seen = [shipment_id for shipment_id in new if shipment_id not in seen]
        if first_seen:
            st.session_state["seen_in_cg_inbox"] = sorted(seen | set(first_seen))
            if not st.session_state.get("selected"):
                st.session_state["selected"] = first_seen[-1]
            st.markdown(
                f'<span class="live">● New mail Recived</span> · '
                f'processing starts on next poll · {len(new)} queued',
                unsafe_allow_html=True,
            )
            return
        with st.status(f"📨 New email received from SU — analyzing… ({len(new)} new)", expanded=True) as status:
            try:
                results = shipment.process_inbox(on_event=status.write)
                status.update(label="Analysis complete", state="complete")
                if results:
                    st.session_state["selected"] = results[-1].shipment_id
            except Exception as e:
                status.update(label="Processing error", state="error")
                st.error(str(e))
        st.rerun()
    else:
        st.markdown(
            f'<span class="live">● Monitoring inbox</span> · last checked {now} · no new mail',
            unsafe_allow_html=True,
        )


monitor()

st.divider()
queue_col, detail_col = st.columns([1, 2.4], gap="large")


# --- Detail render helpers --------------------------------------------------

def _decision_card(result: ShipmentResult) -> None:
    color, bg, label = OUTCOME_STYLE[result.outcome]
    st.markdown(
        f'<div class="decision-card" style="background:{bg};border-left:6px solid {color}">'
        f'<div class="decision-title" style="color:{color}">{label}</div>'
        f'<div class="decision-reason">{html.escape(result.reasoning)}</div></div>',
        unsafe_allow_html=True,
    )


def _trace_panel(result: ShipmentResult) -> None:
    if not result.trace:
        return
    st.markdown("**Pipeline trace**")
    df = pd.DataFrame([{"stage": t.name, "seconds": round(t.seconds, 3)} for t in result.trace])
    st.dataframe(df, hide_index=True, width="stretch")
    total = sum(t.seconds for t in result.trace)
    st.caption(f"total {total:.2f}s · validate/cross-check are deterministic (~0s); time is the LLM hops")


def _cross_panel(result: ShipmentResult) -> None:
    if not result.cross:
        return
    st.markdown("**Cross-document consistency**")
    rows = [
        {
            "field": c.field,
            "result": "agree" if c.status == ConsistencyStatus.AGREE else "DISAGREE",
            **c.values_by_doc,
        }
        for c in result.cross
    ]
    df = pd.DataFrame(rows)
    styled = df.style.apply(
        lambda r: [f"background-color:{'#f0fdf4' if r['result'] == 'agree' else '#fef2f2'}"] * len(r),
        axis=1,
    )
    st.dataframe(styled, hide_index=True, width="stretch")


def _verification(result: ShipmentResult) -> None:
    st.subheader("Verification")
    for doc_name, report in result.reports.items():
        with st.expander(f"📄 {doc_name}", expanded=True):
            df = pd.DataFrame(
                [
                    {
                        "field": r.field,
                        "result": r.status.value,
                        "found": r.found,
                        "expected": r.expected,
                        "confidence": r.confidence,
                        "note": r.note,
                    }
                    for r in report.results
                ]
            )
            styled = df.style.apply(
                lambda row: [f"background-color:{ROW_TINT[row['result']]}"] * len(row), axis=1
            )
            st.dataframe(styled, hide_index=True, width="stretch")
    _cross_panel(result)


def _discrepancies(result: ShipmentResult) -> None:
    flagged = [
        (doc_name, r)
        for doc_name, report in result.reports.items()
        for r in report.mismatches + report.uncertain
    ]
    cross_bad = [c for c in result.cross if c.status == ConsistencyStatus.DISAGREE]
    if not flagged and not cross_bad:
        return
    st.subheader("Discrepancy detail")
    for doc_name, r in flagged:
        field = getattr(result.docs[doc_name], r.field, None)
        snippet = field.source_snippet if field else None
        with st.expander(f"⚠ {r.field} · {doc_name} — {r.status.value}"):
            st.markdown(f"**Found:** {r.found}  \n**Expected:** {r.expected}")
            if r.note:
                st.caption(r.note)
            st.markdown(f"**Source in document:** _{snippet or 'n/a'}_")
    for c in cross_bad:
        with st.expander(f"⚠ {c.field} — disagrees across documents"):
            for doc, val in c.values_by_doc.items():
                st.markdown(f"- **{doc}:** {val}")


def _raw_output(result: ShipmentResult) -> None:
    with st.expander("Raw model output (per document)"):
        for name, doc in result.docs.items():
            st.markdown(f"**{name}**")
            st.json(doc.model_dump())


def _draft(result: ShipmentResult) -> None:
    st.subheader("Draft reply to supplier")
    st.caption("The agent drafts; it never sends. Review, edit, then send.")
    edited = st.text_area("Email", result.draft_reply, height=240, key=f"draft_{result.shipment_id}")
    if st.button(" Approve & send", type="primary"):
        path = inbox.mark_sent(result.shipment_id, edited)
        st.success(f"Sent to {result.sender} (simulated → {path.name})")
        st.rerun()


def _email_view(row: dict) -> None:
    sid = str(_row_value(row, "shipment_id"))
    received = _local_timestamp(_row_value(row, "created_at"), include_date=True)
    subject = str(_row_value(row, "subject", "(no subject)"))
    sender = str(_row_value(row, "sender", "Unknown sender"))
    customer = str(_row_value(row, "customer", "Unknown customer"))
    st.markdown(f"###  {subject}")
    st.markdown(
        f"**From:** {sender}  ·  **To:** CG (Cargo Control)  ·  "
        f"**Customer:** {customer}  ·  **Received:** {received}"
    )
    body = _email_body(sid)
    if body:
        st.markdown(f"> {body}")
    attachments = _attachments(sid)
    if attachments:
        st.markdown(f"**Attachments ({len(attachments)})**")
        cols = st.columns(min(len(attachments), 3))
        for i, (name, data) in enumerate(attachments):
            cols[i % len(cols)].download_button(
                f"📎 {name}",
                data=data,
                file_name=name,
                mime="application/pdf",
                key=f"dl_{sid}_{name}",
                use_container_width=True,
            )


# --- Inbox queue + shipment detail ------------------------------------------

with queue_col:
    st.subheader("Inbox")
    if not ships:
        st.caption("No Mails")
    if ships and not st.session_state.get("selected"):
        st.session_state["selected"] = _row_value(ships[0], "shipment_id")
    for s in ships:
        shipment_id = str(_row_value(s, "shipment_id"))
        subject = html.escape(str(_row_value(s, "subject", "(no subject)")))
        sender = html.escape(str(_row_value(s, "sender", "Unknown sender")))
        doc_count = _row_value(s, "doc_count", 0)
        created_at = _row_value(s, "created_at")
        status = str(_row_value(s, "status", "processing"))
        outcome = _row_value(s, "outcome", None)
        when = _local_timestamp(created_at)
        with st.container(border=True):
            st.markdown(
                f"**{subject}**<br>"
                f"<span style='color:#64748b;font-size:.82rem'>{sender} · 📎 {doc_count or 0} · {when}</span>"
                f"<br>{_badge(status, outcome)}", # type: ignore
                unsafe_allow_html=True,
            )
            if st.button("Open", key=f"open_{shipment_id}", use_container_width=True):
                st.session_state["selected"] = shipment_id

with detail_col:
    selected = st.session_state.get("selected")
    row = storage.get_shipment(selected) if selected else None
    queued_row = queued_by_id.get(str(selected)) if selected else None
    if not row:
        if queued_row:
            _email_view(queued_row)
            st.info("This email is in the CG inbox. Processing will start on the next monitor poll.")
        else:
            st.info("Select a shipment.")
    elif _row_value(row, "status") == "processing":
        st.info(f"📨 {selected} just arrived — agent is processing…")
    elif _row_value(row, "status") == "failed":
        st.error(f"{selected} failed during processing. See the watcher logs.")
    else:
        result = storage.load_shipment_result(selected) # type: ignore
        if result:
            _email_view(row)
            st.divider()
            st.subheader("Agent analysis")
            _decision_card(result)
            _trace_panel(result)
            _verification(result)
            _discrepancies(result)
            _raw_output(result)
            _draft(result)

st.divider()
st.subheader("Ask the data")
st.caption("Plain-English questions over stored shipments, grounded in real SQL.")
question = st.text_input("Question", "Show me everything pending review for ACME Imports Ltd")
if st.button("Ask", disabled=not settings.gemini_api_key):
    with st.spinner("Querying…"):
        try:
            res = nl_query.answer(question)
            st.success(res["answer"])
            with st.expander("Show SQL and rows"):
                st.code(res["sql"], language="sql")
                st.dataframe(res["rows"], hide_index=True, width="stretch")
        except Exception as e:
            st.error(f"Query failed: {e}")
