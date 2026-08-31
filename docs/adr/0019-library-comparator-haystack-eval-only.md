# 0019 - Framework-built comparators (Haystack + LlamaIndex + LangChain/LangGraph), comparison-only, not a production swap

**Status:** Accepted 2026-08-27, revised same day to add LlamaIndex alongside
Haystack, revised again 2026-08-30 to add LangChain/LangGraph - authorizes three
framework-orchestrated RAG implementations strictly inside `comparison/`, for the
vs-managed-rag comparison; does not reopen ADR-0004.

## Context

ADR-0004 rejected LangChain/LangGraph for the **production orchestrator**: hand-rolled
`anthropic`/`openai` calls stay legible for a system this small. That question was
"should `payments_rag/orchestrator.py` use a framework," and the answer stays no.

`docs/vs-managed-rag.md` asks a different question: how does this project's approach
compare against other ways to build a RAG, on an integration/data-exposure axis. It
already compares against an API-hosted product (OpenAI `file_search`) and a manual
consumer tool (NotebookLM). The remaining gap is a real "build it with an off-the-shelf
library" comparator — without one, that bucket in the comparison stays theoretical
instead of measured. ADR-0004 doesn't answer whether the *comparison harness* may use a
framework; it was written about production code, and comparison code living in
`comparison/` is explicitly not that.

## Decision

1. **Add three comparators**, built with **Haystack** (deepset, Apache 2.0),
   **LlamaIndex** (LlamaIndex, Inc., MIT license), and **LangChain + LangGraph**
   (LangChain Inc., MIT license), under `comparison/adapters/`. All index the same two
   corpus PDFs, answer the same 10-question golden set, and log results in the same
   `SystemAnswer` shape (`comparison/schema.py`) as the other systems, scored by the
   same RAGAS + judge pipeline (`comparison/score_comparison.py`,
   `comparison/judge_comparison.py`).
2. **All three, not a subset, because they're independent, actively-maintained answers
   to the same question, and one of them is the one this project's own name-brand
   framework-rejection (ADR-0004) is literally about.** LangChain is the most widely
   adopted framework in this category by mindshare — ahead of both LlamaIndex and
   Haystack, which were already in the comparison — and it had been excluded from the
   comparator roster by inheritance from ADR-0004's *production* stance, not by any
   decision made about the comparison itself. That gap, once noticed, was not
   defensible: ADR-0004 answers "should the production orchestrator use a framework,"
   not "should the comparison measure the most popular one."
3. **LangGraph is not a separate comparator from LangChain.** In real-world usage the
   two are layered, not competing — LangGraph orchestrates control flow, LangChain
   supplies the retrieval/vector-store primitives it calls. The adapter reflects that:
   LangChain builds the index (`InMemoryVectorStore`, `OpenAIEmbeddings`,
   `RecursiveCharacterTextSplitter`), a 2-node LangGraph graph (`retrieve` → `generate`)
   does the control flow, mirroring how Haystack's `Pipeline` and LlamaIndex's
   `query_engine` already do the same job for their own frameworks.
4. **PDFs load via `pypdf` directly, not `langchain_community`'s `PyPDFLoader`.**
   `langchain-community` prints its own deprecation notice as of this writing ("being
   sunset... no longer actively maintained"), and this comparison's own incident
   history (`docs/incidents/2026-08-29-comparison-corpus-and-extraction-bugs.md`)
   already found a real extraction defect in one framework's default PDF reader —
   reason enough to default to the approach already proven reliable (Haystack and
   LlamaIndex's adapters both settled on the same `pypdf`-direct pattern).
5. **Runs isolated**, same pattern as RAGAS and the other two comparators
   (`uv run --isolated --with langgraph --with langchain-openai ...`), never added to
   `pyproject.toml`/`uv.lock`. Same concrete reason as before: adding `ragas` as a real
   dependency earlier in this project silently downgraded the shared venv's `openai`
   package and broke another adapter — a framework with its own pinned transitive
   dependencies risks the same collision.

This does not reopen ADR-0004. `payments_rag/orchestrator.py` stays hand-rolled; this
adds a third measured comparator beside Haystack, LlamaIndex, OpenAI, and NotebookLM,
exactly the way RAGAS already coexists with ADR-0004 as an isolated eval-only
dependency — including for the one framework ADR-0004 names outright.

## Alternatives

- **Pick a subset instead of all three.** Rejected on reflection (see Decision, point
  2) — each is a real, distinct, actively-used answer to "build a RAG with a library,"
  and omitting the single most popular one specifically because it's the one this
  project already has an opinion about would be a selection bias worth calling out,
  not indulging.
- **Treat LangGraph as its own, fourth comparator.** Rejected (Decision, point 3) — it
  doesn't stand alone in real usage; it orchestrates LangChain's own components. A
  separate "LangGraph" entry would misrepresent how the two are actually deployed.
- **Skip a library comparator entirely, argue from the framework's public
  documentation instead.** Rejected: the whole comparison's value is measured numbers
  (RAGAS + judge scores, cost, latency, setup friction), not architecture-diagram
  reasoning; a library bucket without a real measurement would be the weakest entry
  in the piece.
- **Add these frameworks as normal project dependencies instead of isolating them.**
  Rejected for the same reason RAGAS is isolated (point 5) — a comparison-only tool has
  no reason to risk the production venv's pins.

## Consequences

- Three adapters + collectors now exist (`comparison/adapters/haystack_adapter.py`,
  `llamaindex_adapter.py`, `langchain_adapter.py`, and matching `collect_*.py`
  scripts), each with a one-time indexing step (analogous to the OpenAI adapter's
  `setup_vector_store`), and `Makefile` targets (`compare-haystack`,
  `compare-llamaindex`, `compare-langchain`) feeding into `compare-all`.
- `docs/vs-managed-rag.md`'s "libraries first" section currently only evaluates RAGAS
  (as an eval tool). It should get a short addition once results land, distinguishing
  "RAGAS: library that scores a RAG" from "Haystack/LlamaIndex/LangChain: libraries
  you'd build a RAG with" — they answer different questions and shouldn't be conflated
  in the doc.
- Six systems now share one scoring harness (payments-rag, openai-file-search,
  notebooklm, haystack, llamaindex, langchain) — `comparison/score_comparison.py`'s
  `SYSTEMS` dict and `comparison/judge_comparison.py`'s equivalent both carry all six.
