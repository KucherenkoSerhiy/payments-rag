# 0006 — Citations: structured JSON output

**Status:** Accepted (2026-06, scoping v1) — not yet implemented (Week 3)

## Context
The product's trust model is "read the answer, then click through to the exact
spec passage that supports it." That requires the LLM to tell us *which* chunks
it used, reliably enough to render working links.

## Decision
Have the LLM return a structured JSON object `{answer, citations: [chunk_id...]}`
rather than inline citation markers in prose.

## Alternatives
- **Inline markers** (e.g. `[chunk_id=42]` in the answer text). More natural
  phrasing, but broken/hallucinated markers silently produce wrong links, and
  parsing prose is fragile.

## Consequences
- Slightly more rigid prompt; the model must conform to a schema (supported via
  structured outputs / a strict tool).
- Citations are machine-checkable — we can score citation correctness as a
  **separate** signal from answer-text quality (mitigates the scoping risk that a
  judge grades the prose high while the citations point at the wrong chunk).
- Depends on per-chunk stable IDs — already stored (`chunks.id`, plus
  source+page for the human-facing link).
