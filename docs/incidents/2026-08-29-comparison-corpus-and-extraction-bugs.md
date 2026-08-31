# Incident: three silent data-quality bugs in the vs-managed-rag comparison

**Date found:** 2026-08-27 (Bug 1), 2026-08-27/2026-08-29 (Bug 2), 2026-08-29 (Bug 3)
**Date fixed:** all three fixed by 2026-08-29
**Scope:** the RAG comparison work under `comparison/` (`docs/vs-managed-rag.md`,
`docs/adr/0019`) and, for Bug 2, this project's own production corpus/index.
**Severity:** none of these were security or cost incidents. All three silently
produced wrong or misleading *comparison results* — one of them also silently fed
stale content into the production database. No exception was ever raised by any of
the three; each was caught only by noticing an implausible number and inspecting
retrieved content directly.

## Summary

While building two new comparators (Haystack, LlamaIndex — `docs/adr/0019`) for the
RAG-vs-managed-RAG comparison, three unrelated bugs were found and fixed, each one
uncovered only because a downstream number looked wrong enough to investigate rather
than report. None of the three were caused by the comparators' actual RAG
orchestration logic; all three were data-pipeline defects. Fixing all three moved
LlamaIndex's judge-graded factual-correctness score from **67.0/50% pass to
90.5/90% pass** — a result that, left unfixed, would have wrongly supported a
"library RAGs hallucinate more" conclusion in the published comparison.

## Bug 1 — Haystack's sentence-based chunking silently dropped 32% of the index

**Found:** 2026-08-27, during the first Haystack collection run.

**Symptom:** the run completed successfully, but the logged indexing cost
($0.00127) was implausibly low for embedding two ~1.8MB PDFs.

**Root cause:** `DocumentSplitter(split_by="sentence", split_length=10,
split_overlap=2)` was the first, more semantically-sensible-looking choice. PyPDF's
extracted text has no clean sentence boundaries in this corpus's tables and
multi-column layout, so nltk's sentence tokenizer occasionally treated a whole
malformed block as one "sentence" — a chunk exceeding OpenAI's 8192-token embedding
limit. Haystack's `OpenAIDocumentEmbedder` defaults to `raise_on_failure=False`, so
61 of 189 chunks (~32%) were silently excluded from the index; nothing raised.

**Fix:** switched to Haystack's own documented default,
`split_by="word", split_length=200` — caps chunk size directly, independent of
punctuation quality. Re-indexed clean: 577 chunks, zero failures.

**Where:** `comparison/adapters/haystack_adapter.py` (`index_corpus`).

## Bug 2 — a stale test fixture was contaminating retrieval, including production

**Found:** 2026-08-27 (LlamaIndex answered "ten seconds" for SCT Inst's max
execution time — the pre-2025 rule). **Fixed:** 2026-08-29.

**Root cause:** `corpus/raw/sample_sepa.pdf` was a 1.5KB leftover from this
project's earliest pipeline-spike milestone (the W1 spike described in
`CLAUDE.md`), self-labeled *"synthetic fixture"* in its own first line. It
contained: *"An SCT Inst transaction is executed within ten seconds... The maximum
amount per SCT Inst transaction is defined by the scheme..."* — both **pre-2025
rules**, stale relative to the real corpus (current rules: 5 seconds, no scheme-level
limit). Direct reproduction confirmed LlamaIndex retrieved this fixture's chunk
*above* the real rulebook for the execution-time question (cosine similarity 0.482
vs. 0.273) and answered faithfully from what it retrieved — grounded, just in the
wrong document. Not a hallucination.

This file sat in `corpus/raw/`, which every corpus-globbing consumer reads from —
**including this project's own production indexer**
(`payments_rag/indexing/indexer.py:55`, `Path(corpus_dir).glob("*.pdf")`). The live
demo's database was built from this same contaminated corpus. No production-path
question happened to surface the fixture's content during testing, but the exposure
was real, not hypothetical.

**Fix:**
1. Moved `corpus/raw/sample_sepa.pdf` → `corpus/_archive/sample_sepa.pdf` (preserved,
   out of every glob pattern used for real indexing).
2. Confirmed safe first: `tests/test_smoke.py` generates its own synthetic PDF at
   runtime (`smoke_sample.pdf`, in a pytest `tmp_path`) and never referenced the
   archived file by path.
3. Rebuilt the production database: `make index` (reset + reindex from the clean
   2-PDF corpus). Chunk count was unchanged (484 → 484 — the fixture was too small
   to move that number), but the content is now clean.
4. Re-collected and rescored payments-rag, Haystack, and LlamaIndex against the
   clean corpus. `openai-file-search`'s comparator had — by an earlier, separate
   inconsistency — only ever uploaded 2 of the 3 PDFs, so it never saw the fixture
   and needed no changes.

## Bug 3 — LlamaIndex's default PDF reader produced junk and garbled text

**Found:** 2026-08-29, immediately after Bug 2's fix — LlamaIndex *still* answered
"ten seconds" for the execution-time question even with the fixture gone.

**Root cause, two distinct defects, neither present in Haystack's extraction of the
identical PDFs:**

1. Both real corpus PDFs contain an embedded Adobe XMP metadata packet
   (`<?xpacket begin...?>` ... `<?xpacket end="w"?>`) that LlamaIndex's default PDF
   reader (`SimpleDirectoryReader`'s built-in loader; no `llama-index-readers-file`
   extra was installed) dumped into extracted document text verbatim. Confirmed at
   exact byte offsets in both files. This produced a ~4.7KB junk chunk that won a
   top-5 retrieval slot for **every single golden-set question**, not just one.
2. For at least the execution-time question, every one of the 5 retrieved contexts
   was outright garbled, unreadable text — not real prose, likely a font-encoding
   artifact in how the default reader handled this PDF's embedded fonts.

Haystack's `PyPDFToDocument` (`pypdf`, `extraction_mode=PLAIN`) extracts the
identical PDFs as clean, readable prose — confirmed side by side, same question,
same corpus. With nothing usable retrieved, the model fell back on training
knowledge instead of declining, per the "answer only from context" instruction in
the default query prompt — which is what produced the "ten seconds" answer even
after Bug 2 was fixed.

**Fix:** bypassed `SimpleDirectoryReader`'s PDF auto-detection entirely. PDFs are
now loaded with `pypdf` directly (the same library Haystack already uses) inside
the adapter, with an XMP-packet regex strip applied as defense in depth. Re-ran:
the execution-time question now retrieves real prose and answers "5 seconds"
correctly.

**Where:** `comparison/adapters/llamaindex_adapter.py`
(`_load_pdf_documents`, `_XMP_PACKET`).

## Net result

| | Before any fix | After Bug 1 (Haystack) | After Bug 2 (fixture removed) | After Bug 3 (extraction fixed) |
|---|---|---|---|---|
| Haystack judge score | - | 72.1 / 70% pass | 76.5 / 80% pass | (unaffected by Bug 3) |
| LlamaIndex judge score | 67.0 / 50% pass | (unaffected by Bug 1) | 78.5 / 70% pass | **90.5 / 90% pass** |

LlamaIndex's final score is now essentially tied with `openai-file-search`
(90.2/90%) and ahead of Haystack (76.5/80%) — a ~35-point swing entirely
attributable to fixing two silent extraction bugs that had nothing to do with its
actual retrieval/generation orchestration. The comparison's original draft
conclusion — that library-orchestrated RAGs meaningfully underperform on factual
correctness — did not survive this investigation and was not published as stated.

## A fourth thing found and fixed: the resumable-scoring cache itself

While re-scoring after Bug 2's fix, `comparison/judge_comparison.py` completed
suspiciously fast and returned numbers identical to the pre-fix run. Cause: both
`comparison/score_comparison.py` and `comparison/judge_comparison.py`'s
resumable-scoring cache keyed reuse purely on `(system, question_id)` — correct for
retrying a row that failed, wrong for a row whose underlying collected answer
changed underneath it (exactly what re-collecting after a corpus fix does). The
first rescore attempt in this chain silently reused the stale, pre-fix scores.

**Fix:** both scripts now store a `content_hash` (sha256 of the answer, plus
contexts for RAGAS) on every scored row, and only reuse a cached row if that hash
still matches the record's current content. Existing correct rows were backfilled
with their hash rather than re-scored, so this fix did not require re-spending the
API cost already paid for the final, correct numbers above.

## Where the full data trail lives

- Golden-set answers: `data/comparison/{payments_rag,openai_file_search,notebooklm,haystack,llamaindex}.jsonl`
- Scored results: `data/comparison/ragas_scores.jsonl`, `data/comparison/judge_scores.jsonl`
- Comparator code: `comparison/adapters/{haystack_adapter,llamaindex_adapter}.py`
- Decision record: `docs/adr/0019-library-comparator-haystack-eval-only.md`
- Article-facing facts (all above traced with exact source lines): the article
  project's `canonical-facts.md` for this piece, §10
