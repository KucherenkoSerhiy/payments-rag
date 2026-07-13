# 0004 - Raw API calls + light orchestration (no LangChain/LangGraph)

**Status:** Accepted (2026-06, scoping v1)

## Context
The RAG flow is small: embed a question, search pgvector, build a prompt, call
an LLM, parse the response. Frameworks exist to orchestrate exactly this.

## Decision
Write the orchestration by hand with the raw `anthropic` / `openai` SDKs and
plain Python (`retriever.py`, and later an `orchestrator`).

## Alternatives
- **LangChain / LangGraph.** Less glue code, but it hides control flow behind
  abstractions that complicate debugging and add a large learning surface, and it
  churns fast. For a system this small the abstraction isn't worth the opacity.

## Consequences
- More lines written by hand, but every step is legible and debuggable: you can
  read exactly what goes into the prompt.
- If orchestration grows genuinely complex (multi-step agents), revisit. This
  ADR would be superseded, not silently violated.
