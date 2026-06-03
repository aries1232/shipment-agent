"""Minimal UI: run the pipeline on one document and inspect every stage of real state."""

import html
from pathlib import Path

import pandas as pd
import streamlit as st

from src import nl_query, storage
from src.config import settings
from src.orchestrator import run_pipeline
from src.schemas import DecisionOutcome, RunResult

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"

# outcome -> (accent, background tint, label)
OUTCOME_STYLE = {
    DecisionOutcome.AUTO_APPROVE: ("#16a34a", "#f0fdf4", "Auto-approved"),
    DecisionOutcome.HUMAN_REVIEW: ("#d97706", "#fffbeb", "Flagged for human review"),
    DecisionOutcome.AMENDMENT: ("#dc2626", "#fef2f2", "Amendment requested"),
}
ROW_TINT = {"match": "#f0fdf4", "mismatch": "#fef2f2", "uncertain": "#fffbeb"}

st.set_page_config(page_title="Trade Doc Pipeline", page_icon="", layout="wide")
storage.init_db()

st.markdown(
    """
    <style>
      .block-container {padding-top:3rem;max-width:1080px;}
      .hero-title {font-size:2.4rem;font-weight:800;margin:0;
        background:linear-gradient(90deg,#6366f1,#8b5cf6);
        -webkit-background-clip:text;-webkit-text-fill-color:transparent;}
      .hero-sub {color:#64748b;margin:0 0 2px;font-size:1.02rem;}
      .chip {display:inline-block;background:#eef2ff;color:#4338ca;padding:3px 11px;
        border-radius:999px;font-size:.74rem;font-weight:600;}
      .decision-card {padding:18px 22px;border-radius:14px;margin:6px 0 2px;}
      .decision-title {font-size:1.25rem;font-weight:700;margin-bottom:6px;}
      .decision-reason {color:#475569;font-size:.95rem;line-height:1.55;}
      div[data-testid="stMetric"] {background:#f6f7fb;border:1px solid #eceef4;
        border-radius:12px;padding:12px 16px;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<p class="hero-title">Nova</p>', unsafe_allow_html=True)
st.markdown('<p class="hero-sub">Multi-Agent Trade Document Pipeline</p>', unsafe_allow_html=True)
st.markdown(
    '<span class="chip">extract → validate → decide · gemini-3.1-flash-lite</span>',
    unsafe_allow_html=True,
)
st.write("")

if not settings.gemini_api_key:
    st.warning("GEMINI_API_KEY is not set. Add it to `.env` to run the pipeline.")

with st.sidebar:
    st.subheader("Recent runs")
    runs = storage.recent_runs()
    if runs:
        st.dataframe(runs, hide_index=True, width="stretch")
    else:
        st.caption("No runs yet — process a document to populate this.")


def _decision_card(result: RunResult) -> None:
    accent, bg, label = OUTCOME_STYLE[result.decision.outcome]
    st.markdown(
        f'<div class="decision-card" style="background:{bg};border-left:6px solid {accent}">'
        f'<div class="decision-title" style="color:{accent}">{label}</div>'
        f'<div class="decision-reason">{html.escape(result.decision.reasoning)}</div></div>',
        unsafe_allow_html=True,
    )


def _summary(result: RunResult) -> None:
    report = result.report
    cols = st.columns(4)
    cols[0].metric("Fields checked", len(report.results))
    cols[1].metric("Matched", len(report.results) - len(report.mismatches) - len(report.uncertain))
    cols[2].metric("Mismatched", len(report.mismatches))
    cols[3].metric("Uncertain", len(report.uncertain))


def _render(result: RunResult) -> None:
    _decision_card(result)
    _summary(result)

    if result.decision.amendment_request:
        with st.expander(" Drafted amendment request", expanded=True):
            st.markdown(result.decision.amendment_request)

    st.subheader("Extracted fields")
    st.dataframe(
        [
            {"field": name, "value": f.value, "confidence": f.confidence}
            for name, f in result.extracted.items()
        ],
        column_config={
            "confidence": st.column_config.ProgressColumn(
                "confidence", min_value=0, max_value=1, format="%.2f"
            )
        },
        hide_index=True,
        width="stretch",
    )

    st.subheader("Validation")
    df = pd.DataFrame(
        [
            {
                "field": r.field,
                "result": r.status.value,
                "found": r.found,
                "expected": r.expected,
                "note": r.note,
            }
            for r in result.report.results
        ]
    )
    styled = df.style.apply(
        lambda row: [f"background-color:{ROW_TINT[row['result']]}"] * len(row), axis=1
    )
    st.dataframe(styled, hide_index=True, width="stretch")


run_tab, ask_tab = st.tabs(["Run pipeline", "Ask the data"])

with run_tab:
    samples = sorted(p.name for p in SAMPLES_DIR.glob("*.pdf")) if SAMPLES_DIR.exists() else []
    left, right = st.columns(2)
    choice = left.selectbox("Pick a sample", ["— upload my own —", *samples])
    upload = right.file_uploader("…or upload a document", type=["pdf", "png", "jpg", "jpeg"])

    if choice != "— upload my own —":
        doc_name, doc_bytes = choice, (SAMPLES_DIR / choice).read_bytes()
    elif upload is not None:
        doc_name, doc_bytes = upload.name, upload.getvalue()
    else:
        doc_name, doc_bytes = None, None

    if st.button("Run pipeline", type="primary", disabled=doc_bytes is None):
        with st.spinner("Running extract → validate → decide…"):
            try:
                st.session_state["result"] = run_pipeline(doc_bytes, doc_name)
            except Exception as e:
                st.session_state["result"] = None
                st.error(f"Pipeline failed: {e}")

    if st.session_state.get("result"):
        _render(st.session_state["result"])
    else:
        st.info("Pick a sample..")

with ask_tab:
    st.caption("Plain-English questions over stored runs. Answers are grounded in real SQL.")
    question = st.text_input("Question", "How many shipments were flagged this week?")
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
