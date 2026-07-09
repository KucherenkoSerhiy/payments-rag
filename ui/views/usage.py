"""Usage view — runtime observability from the query log (the operator's view)."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # app root

from payments_rag import query_log  # noqa: E402

st.title("Usage")
st.caption("What's actually being asked — from the local query log. (Cost isn't tracked yet.)")

rows = query_log.read_queries(limit=100)
if not rows:
    st.info("No queries logged yet. Ask something on the Ask page and it'll show up here.")
    st.stop()

wall_times = [r["wall_s"] for r in rows if "wall_s" in r]
a, b, c = st.columns(3)
a.metric("questions logged", len(rows))
b.metric("avg latency", f"{sum(wall_times) / len(wall_times):.1f}s" if wall_times else "—")
c.metric("slowest", f"{max(wall_times):.1f}s" if wall_times else "—")

st.subheader("Recent questions")
for r in rows[:25]:
    st.write(f"`{r['at'][11:19]}` · {r['wall_s']:.1f}s · {r['mode']} — {r['question']}")
