"""Evals view — retrieval recall (live) and the last answer-quality run (developer's view)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # app root

from evals import retrieval_eval  # noqa: E402

_ANSWER_EVAL = Path(__file__).resolve().parents[2] / "data" / "last_answer_eval.json"

st.title("Evals")
st.caption("Quality against the golden set — for the developer, not the end user.")

st.subheader("Retrieval — recall@k")
c1, c2 = st.columns(2)
mode = c1.selectbox("Mode", ["vector", "hybrid"], help="rerank is CLI-only (slow)")
k = c2.slider("k", 1, 10, 5)

if st.button("Run retrieval eval", type="primary"):
    with st.spinner("Embedding the golden questions and searching…"):
        res = retrieval_eval.evaluate(k=k, hybrid=(mode == "hybrid"))
    st.metric(
        f"recall@{k} · {res['mode']}",
        f"{res['recall']:.2f}",
        help=f"{res['answered']} labelled questions",
    )
    st.caption(f"ran in {res['duration_s']}s")
    for p in res["per_question"]:
        if p["hit"] is None:
            st.write(f"⚪ {p['id']} — not labelled")
        else:
            st.write(f"{'🟢' if p['hit'] else '🔴'} {p['id']}")

st.divider()

st.subheader("Answers — quality (last run)")
if _ANSWER_EVAL.exists():
    data = json.loads(_ANSWER_EVAL.read_text(encoding="utf-8"))
    a, b, c = st.columns(3)
    a.metric("mean score", data["mean"])
    b.metric(f"pass rate (≥{data['threshold']})", f"{round(data['pass_rate'] * 100)}%")
    c.metric("last run", data["at"].replace("T", " "))
    st.caption(f"ran in {data.get('duration_s', '?')}s")
    for p in data["per_question"]:
        st.write(f"**{p['score']:3d}** · {p['id']} — {p['critique']}")
else:
    st.info(
        "No answer-eval run saved yet. Run `python -m evals.answer_eval` to populate "
        "this (slow: ~10 Claude + 10 GPT-4 calls)."
    )
