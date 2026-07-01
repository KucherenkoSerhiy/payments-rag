# 0008 — Chunk per page (citation accuracy over cross-page context)

**Status:** Accepted 2026-07-01

## Context
The indexer splits each document into chunks before embedding. A chunk carries
`source` + `page` metadata so an answer can cite an exact location. How chunks
relate to page boundaries is a design choice.

## Decision
Chunk **within each page** — a chunk never spans two pages.

## Alternatives
- **Concatenate the whole document, then chunk.** Keeps ideas that straddle a
  page break intact (better context), but a chunk can then contain text from two
  pages, so "which page do I cite?" becomes ambiguous.

## Convincing points / rationale
- The product's entire value proposition is **verifiable citations** — "click and
  confirm on the exact page." Fuzzy page attribution directly undermines that.
- The cost (an idea split across a page seam becomes two half-chunks) is real but
  bounded, and **overlap** partly mitigates it within a page.
- Precise page numbers also make the human-facing link trivial (`source p35`).

## Consequences
- Exact, unambiguous citations — aligned with the core value prop.
- Some context loss at page seams; if evals later show this hurts recall, revisit
  (e.g. allow a chunk to carry a small tail from the previous page while still
  attributing to its dominant page). That would be a new ADR.
