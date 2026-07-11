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
- [x] **Reranking — cross-encoder** — built (LLM-as-reranker), measured
      recall@5 0.60→0.70 (rescued `sct-inst-currency`, exactly the @20 ceiling);
      eval-only, not in the product path (latency). ADR-0016. Hand-written.
- [ ] Breaking the retrieval ceiling — query expansion, HyDE, multi-query, late
      interaction (ColBERT)
- [ ] Deeper answer eval — faithfulness / groundedness vs answer-correctness; RAGAS
- [ ] Agentic patterns — tool use / function calling (same structured-output machinery)
- [ ] Containerization & cloud deploy (for M8)

**Practice:** capture each topic as we go (labels slip otherwise) — state the
*problem* first, then the concept, then a diagram. Running term list in
`docs/glossary.md`.

---

## Public-access & multi-user concerns (evaluate at M7/M8)

Once deployed it's **one app for everyone** — no accounts in scope, but be explicit
about each concern, including the ones we deliberately skip. Writeup:
`docs/writeups/going-public-shared-corpus-rag.md`.

- **Data isolation / tenancy — N/A (deliberately).** The corpus is the shared,
  public SEPA rulebooks; no per-user documents. The hard part of multi-tenant RAG
  doesn't apply. Revisit only if per-user upload is ever added.
- **Access control — near-term (M7/M8).** Ask is public; Evals / Usage / Health are
  dev/admin/ops. Gate those routes (shared admin token / basic-auth). Today
  everything is open.
- **Data privacy — near-term (M7/M8).** The query log (Usage tab) stores every
  question in plaintext and exposes them — a leak once public. Also: questions go
  to third-party LLM APIs. Mitigations: gate/anonymize the log, set retention, add
  a short privacy note, avoid logging obvious PII.
- **Abuse & cost — near-term (M7/M8).** Public + paid-per-call = anyone can run up
  the bill. Per-IP rate limiting + a global daily budget cap + input-length caps
  (revisits ADR-0013's abuse guard).
- **CORS / secrets / TLS — deploy hygiene (M8).** `allow_origins=["*"]` is dev-only
  — tighten to the frontend origin. Managed secrets, HTTPS.
- **Accounts / identity — deferred (out of scope).** If personalization or quotas
  are ever wanted, the FastAPI layer is the seam: auth middleware → per-request
  user → per-user history (off localStorage) → role-gated routes. Core unchanged.

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
- **2026-07-11 (Angular frontend live — ADR-0017 fully implemented)** — Built the
  Angular 20 SPA (`frontend/`) over the FastAPI backend: top nav with role-labeled
  tabs + all four views — **Ask** (cited answer + timing + cost + evidence),
  **Evals** (live recall@k with duration + saved answer-eval), **Usage** (metrics +
  recent), **Health** (5-dependency live checks + Check-all + 10-min auto-check).
  Verified all four in-browser (Playwright) end-to-end against the real Python core
  (Ask 8.1s/$0.0031 with 3 evidence cards; recall@5=0.60 in 3.23s; health all-green).
  Icons via a locally-bundled Tabler webfont. Streamlit superseded (ADR-0017).
- **2026-07-11 (UI pivot: Angular + FastAPI)** — Streamlit did its job (three-view
  glass-box app, measured + observable) but hit its design ceiling. Decided to
  rebuild the frontend as an Angular SPA over a FastAPI backend (ADR-0017,
  supersedes ADR-0010); the API layer is also what M8 needs. Captured the current
  Streamlit state (`docs/writeups/ui-current-state-streamlit.md`) + role-labeled
  nav and a full multi-dependency Health view in the mockups. Backend migration
  starts now (FastAPI: ask / evals-with-duration / usage / health).
- **2026-07-09 (UI: three-view app + a real latency bug)** — Streamlit multipage
  app (`st.navigation`): **Ask** (cited answers + evidence + per-stage timing),
  **Evals** (live retrieval recall@k + last saved answer-eval), **Usage**
  (query-log telemetry). Shared **Health** panel (DB status/latency/last-check).
  New `query_log` (JSONL) — the request-logging layer Usage needed.
  `retrieval_eval.evaluate()` + `answer_eval` result-saving added for the UI. All
  three views verified in-browser. **Fixed a ~10s-per-query DB hang**: `.env`'s
  `DATABASE_URL` used `localhost` → Windows IPv6 detour; normalized to `127.0.0.1`
  in config (+ `connect_timeout`). The Health check caught it (10137ms → 27ms).
- **2026-07-09 (Reranking, Track B)** — Built a cross-encoder reranker as a
  learning exercise (LLM-as-reranker: fanout → rescore each pair → top-k).
  **recall@5 = 0.70** (from vector 0.60) — exactly the vector recall@20 ceiling,
  so it promoted every *fetchable* relevant page into the top-5. Rescued
  `sct-inst-currency` (the M4 answer-eval 0). The eval ran ~10 min (200 sequential
  Haiku calls) → kept eval-only, out of the interactive path on latency grounds; a
  local cross-encoder would be the product answer. ADR-0016. `order_by_relevance` +
  `rerank_retrieve` hand-written (5th hands-on piece) + fast seam-stubbed tests.
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
