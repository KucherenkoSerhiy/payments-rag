# Roadmap & Backlog

The single source of truth for where we are and what's left. Two goals, two
tracks. Updated as things ship. If it's not here, it's lost — so it's all here.
The gaps in `architecture.md`'s final section are mirrored into the backlog below
(keep the two in sync).

## Vision
Build the tool myself rather than use one; make it public so others can integrate
or use it; build my name in the process. Ongoing hobby at a sustainable pace —
not a deadline sprint.

---

## Track A — Product (goal: running in the cloud, usable by others)

Rough order; each milestone is shippable on its own.

- [x] **M0 Foundations** — repo, Docker pgvector, all integrations proven (spike)
- [x] **M1 Retrieval working** — corpus indexed (484 chunks), chunker + boilerplate
      strip, retriever, query CLI + Streamlit UI
- [ ] **M2 Measured retrieval** ← **NEXT** — golden set (question → relevant pages)
      + recall@k eval. Turns "seems good" into a number.
- [ ] **M3 Answer layer** — orchestrator: retrieved chunks → prompt → LLM →
      `{answer, citations}` (structured JSON, ADR-0006)
- [ ] **M4 Answer eval** — cross-model LLM-as-judge (ADR-0007) + golden Q&A set
      (ADR-0012); accuracy number documented in README
- [ ] **M5 Reliability** — API retry/timeout/circuit-breaker; smoke test; CI
      (GitHub Actions running unit + a small eval subset)
- [ ] **M6 Retrieval quality** — reranking / hybrid (vector+BM25) / semantic
      chunking — each adopted only if the eval (M2) shows it helps
- [ ] **M7 Open-source polish** — LICENSE (MIT); README for outsiders; PR
      template; push to public GitHub
- [ ] **M8 Cloud deploy** — containerize the app; managed Postgres+pgvector;
      secrets; rate-limiting/abuse guard (revisits ADR-0013)
- [ ] **M9 Robust ingestion** — layout-aware extraction (PyMuPDF/Docling);
      image/scanned PDFs via OCR or a vision model

**Where we are:** end of M1, starting M2.

---

## Track B — Skill (goal: advanced Python + RAG, writing code myself)

- [x] Read & understand the codebase (modules + tests reviewed)
- [ ] **Write a component yourself** — start small; the M2 recall@k scorer is a
      good first one (simple, pure-Python, testable)
- [ ] RAG evaluation metrics — recall@k, precision@k, MRR; retrieval vs answer eval
- [ ] Prompt construction + structured outputs (for M3)
- [ ] Reliability patterns — retry, timeout, circuit breaker, idempotency (for M5)
- [ ] Containerization & cloud deploy (for M8)
- [ ] Postgres operators / indexing internals (partially covered)

Honest note: "advanced" is a several-month arc and needs you writing real Python,
not just reviewing. The tracker flags hands-on opportunities as they come up.

---

## Full backlog (grouped — nothing dropped)

- **Next:** M2 retrieval eval (needs your question→page labels).
- **Reliability:** retry/timeout/circuit-breaker; smoke test; CI.
- **Quality (only when measurable):** reranking; hybrid search; semantic chunking.
- **Retrieval scoping:** `nearest` searches the whole table — add a per-source
      filter (e.g. search only one rulebook). [architecture.md gap]
- **Public:** LICENSE; outsider README; PR template; public GitHub remote.
- **Cloud:** app Dockerfile; managed pgvector; secrets; rate-limit.
- **Ingestion research:** layout-aware extraction; image/OCR PDFs.
- **Cleanups:** remove `clean_page` U+FFFD no-op (+ its test — see ADR-0009);
      keep README status current.
- **Review remaining (optional):** `spike/` (throwaway), `infra/`, the Postgres
      operators deep-dive.

---

## Status log
- **2026-07-01** — Retrieval working (M1). Chunking iterated → measured neutral
  on retrieval (ADR-0009). ADRs (13) + architecture diagrams written. Streamlit
  import bug fixed. Indexer refactored into `CorpusIndexer`. Mindset reframed to
  public hobby. Next: M2 retrieval eval.
