# 0004 — Raw API calls + light orchestration (no LangChain/LangGraph)

**Status:** Accepted (2026-06, scoping v1)

## Context
The RAG flow is small: embed a question, search pgvector, build a prompt, call
an LLM, parse the response. Frameworks exist to orchestrate exactly this.

## Decision
Write the orchestration by hand with the raw `anthropic` / `openai` SDKs and
plain Python (`retriever.py`, and later an `orchestrator`).

## Alternatives
- **LangChain / LangGraph.** Less glue code, but hides control flow behind
  abstractions that complicate debugging, add a large learning surface, and churn
  fast. For a system this small the abstraction isn't worth the opacity.

## Consequences
- More lines written by hand, but every step is legible and debuggable — you can
  read exactly what goes into the prompt.
- Stronger interview signal: you understand each layer of the RAG stack rather
  than "I called a chain."
- If orchestration grows genuinely complex (multi-step agents), revisit — this
  ADR would be superseded, not silently violated.
