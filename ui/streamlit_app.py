"""Streamlit UI — Ask: cited answers over the SEPA rulebooks (the glass box).

    uv run streamlit run ui/streamlit_app.py

Type a question, get a grounded answer, and see the exact rulebook passages it was
built from (source + page). This is the "Ask" view; Evals and Usage are later
pages (see docs/ROADMAP.md). Needs the DB up and the Anthropic key set.
"""

from __future__ import annotations

import sys
from pathlib import Path
from time import perf_counter

import streamlit as st

# Streamlit runs this file from ui/, so the app root isn't on sys.path by
# default — add it so `payments_rag` (one level up) is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from payments_rag.adapters import db  # noqa: E402  (import after sys.path bootstrap)
from payments_rag.orchestrator import answer  # noqa: E402

st.set_page_config(page_title="Payments RAG — Ask", page_icon="🔎")
st.title("Payments RAG")
st.caption(
    "Ask about the SEPA SCT / SCT Inst rulebooks. Every answer shows the passages "
    "it was built from — verify against the cited page."
)


@st.cache_resource
def _corpus_summary() -> list[tuple[str, int]]:
    with db.connect() as conn:
        return db.source_counts(conn)


with st.sidebar:
    st.subheader("Indexed corpus")
    try:
        for source, n in _corpus_summary():
            st.write(f"- `{source}` — {n} chunks")
    except Exception as exc:  # DB down, not indexed, etc.
        st.warning(f"Corpus unavailable: {exc}")
    k = st.slider("Passages to retrieve", 1, 10, 5)

with st.form("ask"):
    question = st.text_input(
        "Ask a question", value="How fast does an SCT Inst payment settle?"
    )
    submitted = st.form_submit_button("Ask", type="primary")

if submitted and question.strip():
    try:
        wall_t0 = perf_counter()
        with st.spinner("Retrieving passages and generating a grounded answer…"):
            with db.connect() as conn:
                result = answer(conn, question, k=k)
        wall_s = perf_counter() - wall_t0
    except Exception as exc:  # DB down, missing key, API error
        st.error(f"Couldn't answer that: {exc}")
        st.stop()

    st.markdown("### Answer")
    st.write(result.answer)
    # wall_s is the true server-side time; the two stages are sub-parts, and
    # "other" (connect + anything uninstrumented) is what the old sum hid.
    other_s = max(0.0, wall_s - result.retrieval_s - result.generation_s)
    st.caption(
        f"⏱ {wall_s:.1f}s server · retrieval {result.retrieval_s:.1f}s "
        f"· generation {result.generation_s:.1f}s · connect + overhead {other_s:.1f}s"
    )

    st.markdown("### Evidence")
    st.caption("The passages this answer is built from — open the page to verify.")
    if not result.citations:
        st.info("The model cited no specific passage. Treat the answer with extra caution.")
    for c in result.citations:
        passage = " ".join(c.text.split())
        with st.container(border=True):
            st.markdown(f"**{c.source} · p{c.page}**")
            st.write(passage[:700] + ("…" if len(passage) > 700 else ""))
