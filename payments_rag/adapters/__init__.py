"""Adapters — thin wrappers around external services (Postgres, OpenAI, Anthropic).

Ports & Adapters: everything that talks to the outside world lives here, so the
indexing/retrieval/orchestration code depends on small local seams, not SDKs.
"""
