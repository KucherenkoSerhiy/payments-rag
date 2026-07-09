"""Payments RAG — multi-view app entry (Ask / Evals / Usage).

    uv run streamlit run ui/streamlit_app.py

Three views behind a nav switch, each for a different person:
  - Ask   — cited answers (the user)
  - Evals — quality vs the golden set (the developer)
  - Usage — runtime observability from the query log (the operator)

The sidebar Health panel (DB status + latency + last-checked) is shared across all.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # app root

from payments_rag.adapters import db  # noqa: E402

st.set_page_config(page_title="Payments RAG", page_icon="🔎")


@st.cache_data(ttl=30)
def _health() -> dict:
    """Ping the DB; cached 30s so the check fires at most twice a minute."""
    at = datetime.now().strftime("%H:%M:%S")
    try:
        t0 = perf_counter()
        with db.connect() as conn:
            conn.execute("SELECT 1")
        return {"ok": True, "ms": round((perf_counter() - t0) * 1000), "at": at}
    except Exception as exc:  # DB down / unreachable
        return {"ok": False, "error": str(exc), "at": at}


with st.sidebar:
    st.subheader("Health")
    h = _health()
    if h["ok"]:
        st.success(f"DB reachable · {h['ms']} ms · checked {h['at']}")
    else:
        st.error(f"DB unreachable · checked {h['at']}\n\n{h['error']}")

pages = [
    st.Page("views/ask.py", title="Ask", icon="🔎", default=True),
    st.Page("views/evals.py", title="Evals", icon="🧪"),
    st.Page("views/usage.py", title="Usage", icon="📈"),
]
st.navigation(pages).run()
