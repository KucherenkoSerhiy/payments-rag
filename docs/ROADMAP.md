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
- [x] **M2 Measured retrieval** — 10-question verified golden set (both
      rulebooks, diverse themes). **recall@5 = 0.60** (6/10) — the baseline every
      retrieval change is now measured against. Improving it = M6.
- [x] **M3 Answer layer** — `orchestrator.py`: retrieve → grounded prompt → LLM
      → `{answer, citations}` (structured outputs, ADR-0006) → citations mapped to
      source+page. `cli ask` works end-to-end. `build_prompt`/`answer` hand-written.
- [x] **M4 Answer eval** — cross-model LLM-as-judge (GPT-4 grades Claude, ADR-0007)
      + golden Q&A set (10 Q, ADR-0012). **mean 85.5 / pass-rate 90%** (9/10 ≥70).
      The one 0 (currency) is a retrieval miss surfacing as an answer failure —
      generation can't recover what retrieval didn't fetch. `summarize` hand-written.
- [x] **M5 Reliability (lean)** — API timeouts + retries done (60s / 3 retries,
      `config`); smoke test done (`smoke_test.py`, green). Circuit breaker
      skipped (overkill for a single-user app). CI deferred to M7 (needs the
      GitHub remote + service containers).
- [x] **M6 Retrieval quality** — measured all levers: vector 0.60,
      rerank-ceiling 0.70, hybrid 0.60 (neutral trade). Kept vector default;
      hybrid built + retained as an option (`--hybrid`). Further tuning
      deprioritized on a toy corpus. See ADR-0014 (Accepted).
- [ ] **M7 Open-source polish** — LICENSE (MIT); README for outsiders; PR
      template; push to public GitHub
- [ ] **M8 Cloud deploy** — containerize the app; managed Postgres+pgvector;
      secrets; rate-limiting/abuse guard (revisits ADR-0013)
- [ ] **M9 Robust ingestion** — layout-aware extraction (PyMuPDF/Docling);
      image/scanned PDFs via OCR or a vision model

**Where we are:** M0–M6 done. Full loop works and is measured on both axes —
retrieval (recall@5 = 0.60) and answers (mean 85.5 / 90% pass). Next public step
is M7 (open-source polish).

---

## Track B — Skill (goal: advanced Python + RAG, writing code myself)

**Foundational arc — done** (retrieval, eval, generation, structured outputs):
- [x] Read & understand the codebase (modules + tests reviewed)
- [x] Write components yourself — `recall_at_k`, `reciprocal_rank_fusion`,
      `summarize`, `build_prompt`/`answer` (4 hand-written, each tested)
- [x] RAG evaluation metrics — recall@k / precision@k / MRR (retrieval) +
      cross-model LLM-as-judge (answers); both measured (0.60 / 85.5)
- [x] Prompt construction + structured outputs — incl. constrained-decoding
      internals (grammar/FSM + logit masking). See `docs/glossary.md` + diagram.
- [ ] Reliability patterns — timeout + retry configured (M5) but not hand-written;
      circuit breaker / idempotency skipped (single-user). **Partial.**
- [ ] Postgres operators / indexing internals — operators + HNSW + GIN/FTS
      covered; deeper index internals **partial**.

**Frontier — live learning edges** (each documented problem-first, with a diagram):
- [ ] **Reranking — cross-encoder** (next hands-on; targets the measured recall
      ceiling — bi-encoder vs cross-encoder)
- [ ] Breaking the retrieval ceiling — query expansion, HyDE, multi-query, late
      interaction (ColBERT)
- [ ] Deeper answer eval — faithfulness / groundedness vs answer-correctness; RAGAS
- [ ] Agentic patterns — tool use / function calling (same structured-output machinery)
- [ ] Containerization & cloud deploy (for M8)

**Practice:** capture each topic as we go (labels slip otherwise) — state the
*problem* first, then the concept, then a diagram. Running term list in
`docs/glossary.md`.

---

## Full backlog (grouped — nothing dropped)

- **Next:** M2 retrieval eval (needs your question→page labels).
- **Reliability:** retry/timeout/circuit-breaker; smoke test; CI.
- **Quality (only when measurable):** reranking; hybrid search; semantic chunking.
      Off-the-shelf options (ranx, BGE cross-encoder, native-hybrid vector DBs) in
      `docs/prior-art.md` — revisit if retrieval becomes a real bottleneck.
- **Retrieval scoping:** `nearest` searches the whole table — add a per-source
      filter (e.g. search only one rulebook). [architecture.md gap]
- **Public:** LICENSE; outsider README; PR template; public GitHub remote.
- **Cloud:** app Dockerfile; managed pgvector; secrets; rate-limit.
- **Ingestion research:** layout-aware extraction; image/OCR PDFs.
- **Corpus gap:** pacs.* / ISO 20022 message names are absent from the EPC
      *rulebooks* (0 occurrences) — index the EPC Implementation Guidelines to
      cover pacs.* per the stated scope. (Found via the golden set, 2026-07-04.)
- **Cleanups:** remove `clean_page` U+FFFD no-op (+ its test — see ADR-0009);
      keep README status current.
- **Review remaining (optional):** `spike/` (throwaway), `infra/`, the Postgres
      operators deep-dive.

---

## Status log
- **2026-07-06 (M4 done)** — Answer-quality eval: GPT-4 judges Claude's answers
  against a 10-Q reference set (cross-model, ADR-0007). **mean 85.5, pass-rate
  90%** (9/10 ≥70). The single 0 (currency) is a *retrieval* miss — the euro page
  wasn't in the vector top-5, so the answer couldn't state it (ties M3's thesis:
  generation is capped by retrieval; notably the one question hybrid rescues).
  Judge grades completeness tightly (docked extra-but-correct detail) — a prompt
  knob if we want it. `summarize` hand-written (4th hands-on piece).
- **2026-07-06 (M5 lean done)** — API client timeouts (60s) + retries set (kills
  the multi-minute connection stalls). Smoke test (`smoke_test.py`) green
  end-to-end. Circuit breaker skipped; CI deferred to M7.
- **2026-07-04 (M6 done)** — Built hybrid (OR-keyword + vector, RRF). Fair
  measurement: hybrid recall@5 = 0.60 = vector — different mix (gained currency,
  lost recall-deadlines), net neutral. Decision: vector stays default, hybrid
  optional, stop tuning (toy corpus). All levers now measured. ADR-0014 Accepted.
- **2026-07-04 (M6 diagnostic)** — Recall curve: @5=0.60, @10=0.70, @20=0.70
  (plateau). 3/10 questions miss even at top-20 → **recall-bound, not
  rank-bound.** Reranking headroom only +0.10 here; **hybrid search (BM25) is the
  higher-leverage first lever.** See ADR-0014 Measurement.
- **2026-07-04 (M3 done)** — Answer layer works end-to-end (`cli ask` →
  grounded answer + citations to source/page). `build_prompt`/`answer`
  hand-written (2nd hands-on session). Note: answer quality is capped by
  retrieval — the demo answer missed the crisp p26 "5 seconds" figure because
  retrieval didn't surface it (recall@5 = 0.60). Reinforces M6.
- **2026-07-04 (M2 done)** — 10-question verified golden set (domain research;
  pages confirmed from source, not the retriever). **recall@5 = 0.60** (6/10).
  Misses: currency, charging-principle, remittance-length, value-limits — the
  targets for M6 (rerank / hybrid search) or a k sweep. This is the baseline all
  retrieval changes get measured against.
- **2026-07-04 (later)** — Ran M2 end-to-end: recall@5 = 1.00 over 2 verified
  questions (proves the loop; not a quality verdict). Golden-set work caught a
  **corpus gap** — pacs.* absent from the rulebooks → backlog — and a bad
  question type (cross-doc comparison), both fixed in the seed set.
- **2026-07-04** — M2 harness built: `evals/retrieval_eval.py` + golden-set
  YAML + 8 tests. `hit_at_k`/`recall_at_k` written by hand (first hands-on
  Python). Awaiting golden-set page labels to produce the recall@k number.
- **2026-07-01** — Retrieval working (M1). Chunking iterated → measured neutral
  on retrieval (ADR-0009). ADRs (13) + architecture diagrams written. Streamlit
  import bug fixed. Indexer refactored into `CorpusIndexer`. Mindset reframed to
  public hobby. Next: M2 retrieval eval.
