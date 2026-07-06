"""Minimal Streamlit UI for the retrieval checkpoint.

    uv run streamlit run ui/streamlit_app.py

Retrieval only — type a SEPA question, see the spec passages that come back,
with source + page + cosine distance. No generated answers yet (that is the
Week-3 agent layer); this is the query CLI with a box instead of a terminal.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Streamlit runs this file from ui/, so the app root isn't on sys.path by
# default — add it so `payments_rag` (one level up) is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from payments_rag.adapters import db  # noqa: E402  (import after sys.path bootstrap)
from payments_rag.retrieval.retriever import retrieve  # noqa: E402

st.set_page_config(page_title="Payments RAG — retrieval", page_icon="🔎")
st.title("Payments RAG — retrieval")
st.caption(
    "SEPA SCT / SCT Inst spec search. Shows the retrieved passages only — "
    "answer generation is a later milestone. Verify against the cited page."
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

question = st.text_input(
    "Ask a question", value="How fast does an SCT Inst payment settle?"
)

if st.button("Search", type="primary") and question.strip():
    with st.spinner("Embedding question and searching pgvector…"):
        with db.connect() as conn:
            results = retrieve(conn, question, k=k)
    if not results:
        st.info("No results — is the corpus indexed? Run: `cli index --reset`")
    for rank, r in enumerate(results, 1):
        preview = " ".join(r.text.split())
        st.markdown(f"**#{rank} · {r.source} · p{r.page}** — distance `{r.distance:.4f}`")
        st.write(preview[:600] + ("…" if len(preview) > 600 else ""))
        st.divider()
