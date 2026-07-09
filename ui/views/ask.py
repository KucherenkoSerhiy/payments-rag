"""Ask view — cited answers with evidence and per-stage timing (the user's view)."""

from __future__ import annotations

import sys
from pathlib import Path
from time import perf_counter

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # app root

from payments_rag import query_log  # noqa: E402
from payments_rag.adapters import db  # noqa: E402
from payments_rag.orchestrator import answer  # noqa: E402

MODE = "vector"  # orchestrator.answer uses the default vector retriever


@st.cache_resource
def _corpus_summary() -> list[tuple[str, int]]:
    with db.connect() as conn:
        return db.source_counts(conn)


st.title("Ask")
st.caption(
    "Ask about the SEPA SCT / SCT Inst rulebooks. Every answer shows the passages "
    "it was built from — verify against the cited page."
)

with st.sidebar:
    st.subheader("Indexed corpus")
    try:
        for source, n in _corpus_summary():
            st.write(f"- `{source}` — {n} chunks")
    except Exception as exc:  # DB down, not indexed, etc.
        st.warning(f"Corpus unavailable: {exc}")
    k = st.slider("Passages to retrieve", 1, 10, 5)

with st.form("ask"):
    question = st.text_input("Ask a question", value="How fast does an SCT Inst payment settle?")
    submitted = st.form_submit_button("Ask", type="primary")

if submitted and question.strip():
    try:
        wall_t0 = perf_counter()
        with st.spinner("Retrieving passages and generating a grounded answer…"):
            c0 = perf_counter()
            conn = db.connect()
            connect_s = perf_counter() - c0
            try:
                result = answer(conn, question, k=k)
            finally:
                conn.close()
        wall_s = perf_counter() - wall_t0
    except Exception as exc:  # DB down, missing key, API error
        st.error(f"Couldn't answer that: {exc}")
        st.stop()

    query_log.log_query(
        question,
        mode=MODE,
        k=k,
        wall_s=wall_s,
        retrieval_s=result.retrieval_s,
        generation_s=result.generation_s,
        n_citations=len(result.citations),
    )

    st.markdown("### Answer")
    st.write(result.answer)
    other_s = max(0.0, wall_s - connect_s - result.retrieval_s - result.generation_s)
    st.caption(
        f"⏱ {wall_s:.1f}s server · connect {connect_s:.1f}s · retrieval {result.retrieval_s:.1f}s "
        f"· generation {result.generation_s:.1f}s · other {other_s:.1f}s"
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
