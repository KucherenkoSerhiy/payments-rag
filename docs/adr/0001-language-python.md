# 0001 — Implementation language: Python

**Status:** Accepted (2026-06, scoping v1)

## Context
The owner's primary stack is .NET/Angular. The project is an AI/RAG system:
embeddings, a vector DB client, an LLM SDK, PDF parsing, an eval harness.

## Decision
Build in Python.

## Alternatives
- **.NET** (owner's strongest stack). Fastest to write, but the AI ecosystem is
  Python-first — every library choice would fight the grain.
- **Dual .NET + Python** (Semantic Kernel layer). Adds 2–3 days to also expose a
  .NET surface. Not worth it for this project.

## Consequences
- Ramp-up cost working outside the primary stack (mitigated: AI codes, human
  reviews and learns the idioms).
- Access to the mature Python AI ecosystem (`anthropic`, `openai`, `pgvector`,
  `pypdf`, `pytest`).
