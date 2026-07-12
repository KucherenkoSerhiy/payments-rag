# Architecture Decision Records

Each ADR captures one decision: the context, the choice, the alternatives, and
the consequences we accepted. Format is [Michael Nygard's](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
They are immutable once Accepted — a reversal is a *new* ADR that supersedes the
old one, so the history of *why* survives.

Why bother on a solo project: decisions fade from memory and get silently
reversed. An ADR preserves the *why*, so future-you (or a contributor) doesn't
relitigate a settled call.

| # | Decision | Status |
|---|---|---|
| [0001](0001-language-python.md) | Implementation language: Python | Accepted |
| [0002](0002-vector-store-pgvector.md) | Vector store: Postgres + pgvector | Accepted |
| [0003](0003-embedding-model-pinned.md) | Embeddings: `text-embedding-3-small`, pinned | Accepted |
| [0004](0004-raw-api-no-framework.md) | Raw API + light orchestration (no LangChain) | Accepted |
| [0005](0005-production-llm-haiku.md) | Production LLM: Claude Haiku 4.5 | Accepted (supersedes scoping) |
| [0006](0006-structured-json-citations.md) | Citations: structured JSON output | Accepted (not yet built) |
| [0007](0007-cross-model-llm-judge.md) | Eval: cross-model LLM-as-judge | Accepted (not yet built) |
| [0008](0008-per-page-chunking.md) | Chunk per page (citation accuracy) | Accepted |
| [0009](0009-boilerplate-and-sentence-chunking.md) | Boilerplate strip + sentence-aware chunking | Accepted (measured neutral on retrieval) |
| [0010](0010-streamlit-ui.md) | UI: minimal Streamlit | Accepted (superseded by 0017) |
| [0011](0011-repo-layout.md) | Code in its own repository | Accepted |
| [0012](0012-golden-set-in-repo.md) | Golden eval set: YAML in repo | Accepted (not yet built) |
| [0013](0013-deploy-docker-local.md) | Deploy: Docker, local only | Accepted |
| [0014](0014-improve-retrieval-rerank-hybrid.md) | Improve retrieval: rerank / hybrid | Accepted (vector default; hybrid optional) |
| [0015](0015-package-by-concern-llm-adapter.md) | Package by concern; extract LLM adapter | Accepted |
| [0016](0016-reranker-llm-cross-encoder-eval-only.md) | Reranking: LLM-as-cross-encoder, eval-only (Track B) | Accepted (recall 0.60→0.70; not in product path) |
| [0017](0017-frontend-angular-fastapi.md) | Frontend: Angular SPA + FastAPI backend | Accepted (supersedes 0010) |
