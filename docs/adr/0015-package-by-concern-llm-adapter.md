# 0015 — Package by concern; extract an LLM adapter

**Status:** Accepted 2026-07-06

## Context
`payments_rag/` was a flat package of ~9 modules — the folder gave no signal of
the architecture, so finding code meant scanning a list. And the Anthropic LLM
plumbing (`_get_client`, `_llm_json`, schema) lived *inside* `orchestrator.py`,
while the OpenAI adapter (`embedding.py`) was its own clean module — an asymmetry
that made the two `_get_client()`s read oddly side by side.

## Decision
1. **Group modules by concern** into subpackages that mirror the RAG pipeline +
   Ports & Adapters, so the folder tree *is* the architecture ("Screaming
   Architecture"):
   - `adapters/` — `db`, `embedding`, `llm` (external services)
   - `indexing/` — `indexer`, `chunker`, `textprep`
   - `retrieval/` — `retriever`, `fusion`
   - `orchestrator.py` and `config.py` stay at the top.
2. **Extract `adapters/llm.py`** (Anthropic client + `complete_json`) from the
   orchestrator, symmetric with `adapters/embedding.py`. `orchestrator.py` is now
   pure flow: retrieve → build prompt → LLM → map citations.
3. **Adapters stay modules** (functions + a lazy client singleton), not classes.

## Alternatives
- **Package by technical layer** (`controllers/ services/ models/`) — rejected;
  it screams *framework*, not *domain*.
- **A folder per module / deeper nesting** — rejected as over-structuring for ~9
  modules (a `generation/` folder for one file, etc.).
- **`LLMClient` class + a `Protocol` port** (hexagonal, DI-friendly) — deferred.
  YAGNI: one provider, and tests already monkeypatch `adapters.llm.complete_json`
  cleanly. **Upgrade path:** promote to a class + Protocol when a second provider
  or injection-based testing actually appears (its own ADR).

## Consequences
- The tree communicates the architecture; you navigate by concern.
- One-time import churn across the codebase (done; full suite green).
- Two symmetric provider adapters (`embedding`, `llm`); the LLM call is patched
  at `adapters.llm.complete_json` in tests.
- Naming follows domain standards: `adapters/` (Ports & Adapters), `retrieval/`
  (Information Retrieval / the "R" in RAG); `indexing/` chosen over `ingestion/`
  to pair with `retrieval/`.
