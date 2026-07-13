"""Payments RAG — core library.

The framework-free core: indexing (PDF → chunks → embeddings), retrieval (vector
+ hybrid), the answer orchestrator, service adapters (DB, embeddings, LLM),
health checks, the query log, and the CLI. The FastAPI app (`api/`) and the eval
harnesses (`evals/`) sit on top of this package.
"""
