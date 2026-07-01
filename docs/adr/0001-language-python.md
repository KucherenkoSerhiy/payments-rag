# 0001 — Implementation language: Python

**Status:** Accepted (2026-06, scoping v1)

## Context
The owner's primary stack is .NET/Angular. The project is an AI/RAG system:
embeddings, a vector DB client, an LLM SDK, PDF parsing, an eval harness.

## Decision
Build in Python.

## Alternatives
- **.NET** (owner's strongest stack). Fastest to write, but the AI ecosystem is
  Python-first — every library choice would fight the grain, and .NET AI signal
  is weaker for the roles being targeted.
- **Dual .NET + Python** (Semantic Kernel layer). Adds 2–3 days for a second
  audience (MS-stack shops). Deferred, not worth it now.

## Consequences
- Ramp-up cost working outside the primary stack (mitigated: AI codes, human
  reviews and learns the idioms).
- Access to the mature Python AI ecosystem (`anthropic`, `openai`, `pgvector`,
  `pypdf`, `pytest`).
- Demonstrates the owner can operate outside their comfort stack — itself a
  signal for AI-engineering roles.
