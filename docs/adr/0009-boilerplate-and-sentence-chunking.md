# 0009 — Boilerplate stripping + sentence-aware chunking

**Status:** Accepted 2026-07-01 — **measured neutral on retrieval** (kept for other reasons)

## Context
The first indexer used a fixed word-window splitter and fed raw page text
straight to the embedder. Two visible problems: (1) every page repeats a
header/footer (EPC URL + page number, rulebook title, "Date issued"), so that
boilerplate landed in every chunk; (2) word-windows cut mid-sentence, producing
fragments.

## Decision
1. **Strip boilerplate generically** (`textprep.py`): a line that recurs on ≥50%
   of a document's pages is structural. Digits are masked before comparing so
   page numbers (`...eu 35` vs `...eu 36`) don't hide the repeat. Frequency count
   over normalised strings — no ML.
2. **Sentence-aware chunking** (`chunker.py`): split on sentence boundaries and
   pack whole sentences to ~`size` words with sentence-level overlap.

## Rationale (the hypothesis)
Boilerplate is identical across all chunks, so it adds a shared component to
every vector; the theory was that this flattened the similarity signal (query
distances were all clustered ~0.34). Cleaner, sentence-aligned chunks should
embed to sharper points and spread the distances.

## Measured outcome — the hypothesis was wrong
Re-indexed (495 → 484 chunks) and re-ran the same query. Boilerplate **was**
removed from the chunk text (verifiable win for cleanliness). But retrieval
**did not change**: same top pages, distances essentially flat (0.34 → 0.34,
marginally higher). Cosine distance is normalised and direction-based, so a
constant component shared by all chunks barely affects query-relevance ranking.
The ~0.34 floor is just this dense, homogeneous legal corpus.

## Consequences
- **Kept** anyway: clean chunks matter for citations and for the eventual LLM
  prompt (no junk fed to the model) — just not for retrieval ranking.
- **The real lesson:** you cannot judge a chunking change by eyeballing one
  query. Chunking/retrieval changes must be measured against a golden set
  (recall@k). This ADR is the concrete evidence for the "don't tune chunking
  blind — build the eval first" discipline.
- Aside: the `�` seen in terminal output was **not** corruption — valid Unicode
  (U+2022 bullet, U+2018/9 curly quotes) the Windows console can't render.
