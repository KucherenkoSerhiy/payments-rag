# ADR-0020: Screaming-architecture restructure of the core and comparison harness

Date: 2026-08-31
Status: accepted

## Context

An architecture audit (2026-08-31) mapped every class against Clean
Architecture / DDD layering. Verdict: the codebase was largely healthy (16 of
18 classes single-responsibility), but the layout didn't say what the system
does, and a handful of real seams were misplaced:

- `orchestrator.py` sat loose at the package root; the value objects
  (`Citation`, `AnswerResult`, `RetrievedChunk`, `IndexStats`) lived inside
  whichever flow file happened to use them.
- The `/ask` route held a complete use case (answer + spend ledger +
  telemetry), so the CLI could not reuse it, and the flow was untestable
  outside `TestClient`.
- `CorpusIndexer` owned PDF extraction inline, though the comparison work
  (docs/incidents/2026-08-29) proved a PDF reader is a swappable component
  that silently breaks everything downstream.
- `RateLimiter` mixed a framework-free sliding-window algorithm with FastAPI
  exception handling.
- Three comparison collectors were the same 30 lines, three times.

## Decision

Name the packages after the RAG loop's capabilities and give each block one
home:

1. **`payments_rag/domain.py`** - the shared value objects. Pure data,
   imports nothing; every layer speaks in these types.
2. **`payments_rag/answering/`** - `orchestrator.py` (the pure answer flow,
   moved from the package root) plus `service.py`, the extracted deployed-ask
   use case (answer + wallet spend + query telemetry). The API route is now
   request-in/response-out. The CLI's `ask` intentionally keeps calling the
   orchestrator directly: owner-local runs must not consume the public
   deploy's budget or pollute its Usage telemetry.
3. **`payments_rag/adapters/pdf.py`** - PDF extraction pulled out of
   `CorpusIndexer`, making the reader an explicit adapter seam beside
   db/embedding/llm.
4. **`api/rate_limit.py`** - the sliding-window counter, framework-free;
   `api/guard.py` keeps only HTTP policy (429 mapping, budget gate).
5. **`comparison/adapters/base.py`** - the framework comparators' shared
   contract (`build(pdfs) -> RagSystem`), and every adapter restructured into
   the article's architecture blocks as named methods: Indexer
   (`extract_text` / `chunk` / `embed_corpus` / `store`), Retriever
   (`embed_question` / `search`), Generator (`build_prompt` / `generate`)
   where the system exposes those seams (Haystack; LangChain's two graph
   nodes), and an explicit `retrieve_and_generate` where it fuses them
   (LlamaIndex's query engine, OpenAI's file_search call) - the method name
   states the fusion instead of faking a seam.
6. **`comparison/collect/`** - one package for all collectors, sharing
   `base.collect(system, entries, answer_one)`: golden set in, one appended
   JSONL row per answer out, uniform per-question logging. `framework.py`
   (lazy import keeps each framework in its own `uv --isolated` env) replaces
   the three identical scripts; `payments_rag` / `openai_filesearch` /
   `notebooklm` keep only their genuinely different setup lines.
7. **`scripts/smoke_live.py`** - the live pre-push smoke moved off the app
   root (it hits real APIs, so it is not a pytest test).

## Deliberately not done

- **No `Protocol`/DI inversion in the core.** ADR-0015's call stands: module
  functions until a second provider or DI-based testing forces the issue.
  Neither has happened; tests monkeypatch the adapter seams cleanly.
- **No behavior changes.** Same prompts, models, costs, logging, cache
  hashes; collected JSONL data and both scorers' caches remain valid.
- **payments-rag / openai / notebooklm collectors stay separate.** They are
  genuinely different shapes (live DB connection; vendor-side persistent
  store setup; manual replay), not copy-paste.

## Consequences

- The tree now reads as the system: `domain / indexing / retrieval /
  answering / adapters` mirror the article's own block diagram.
- One place to fix a collector bug instead of three.
- The ask flow is unit-testable without HTTP, and a future entry point
  (a queue worker, a bot) reuses `answering.service` as-is.
- Old import paths (`payments_rag.orchestrator`,
  `payments_rag.retrieval.retriever.RetrievedChunk`) are gone; external
  notebooks/scripts must update. `docs/architecture.md`'s module map is
  updated in the same change.
