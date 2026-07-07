# Glossary

A running list of the terms this project has passed through — kept so the labels
don't slip even when the underlying idea is solid.

**Convention:** most entries are written *problem-first* — what goes wrong without
the thing, then what the thing is. That's the order they were actually learned in,
and the one that sticks. New topics get a short problem-first note (and usually a
diagram) as we hit them; the term lands here afterward.

---

## Retrieval & RAG

- **RAG (Retrieval-Augmented Generation)** — retrieve relevant text, then have an
  LLM answer *using* it. Problem: an LLM doesn't know your private/niche corpus and
  will hallucinate; grounding the answer in fetched passages fixes both.
- **Corpus** — the body of source documents you index (here: the EPC SCT and
  SCT Inst rulebooks).
- **Chunk** — a passage-sized slice of a document; the unit that gets embedded and
  retrieved. Problem: a whole PDF is too big to embed or cite precisely.
- **Chunking strategy** — how you cut documents (fixed-size, sentence, semantic).
  Problem: bad cuts split one answer across two chunks, or pad a chunk with noise.

## Embeddings & vector indexing

- **Embedding** — text turned into a fixed-length vector (here 1536 numbers) so
  similar meanings sit close together. Problem: computers can't compare *meaning*
  directly; a vector turns "similar" into a measurable distance.
- **pgvector** — a Postgres extension that stores vectors and adds distance
  operators. Problem: keeps vectors beside your relational data, no separate DB.
- **HNSW** — an approximate-nearest-neighbour index (a navigable graph). Problem:
  exact search over millions of vectors is slow; HNSW trades a little accuracy for
  a lot of speed.
- **Distance operators** — `<=>` cosine, `<->` L2/Euclidean, `<#>` inner product.
  Problem: "closeness" has several definitions; pick the one the embeddings were
  trained for (cosine, for OpenAI models).
- **Dimensionality (1536)** — the length of the vector, fixed per embedding model.
  Problem: changing the model/dim invalidates every vector already stored.

## Search & ranking

- **Vector / semantic search** — rank chunks by embedding distance to the query.
  Catches meaning even when the words differ.
- **Keyword / full-text search (FTS)** — Postgres `to_tsvector` / `tsquery`, ranked
  by `ts_rank`, backed by a GIN index. Problem: vector search can miss exact tokens
  (codes, "SHARE", "euro"); keyword search nails literal matches.
- **Hybrid search** — combine vector + keyword results. Problem: each alone misses
  cases the other catches.
- **Reciprocal Rank Fusion (RRF)** — merge ranked lists by summing `1/(k0+rank)`
  (k0=60). Problem: two lists have scores you can't compare; their *ranks* are
  comparable, so you fuse on rank.
- **Bi-encoder** — embeds query and document *separately*, then compares the two
  vectors (what we use). Fast, but never sees the pair together.
- **Cross-encoder / reranker** — feeds query + document *together* through a model
  for one relevance score. Problem: bi-encoders miss fine-grained relevance;
  cross-encoders are sharper but too slow to run over the whole corpus — so they
  re-rank only the top-k a bi-encoder already fetched.

## Generation & prompting

- **Prompt construction / grounding** — assembling the LLM input from the question
  + retrieved chunks, with instructions to answer *only* from them. Problem:
  ungrounded models invent facts.
- **Citations** — mapping each answer back to source + page. Problem: for a spec,
  an unsourced answer isn't trustworthy; the reader must be able to verify.

## Structured outputs

- **Structured outputs** — forcing the model's reply to match a JSON schema.
  Problem: free text is unparseable; downstream code needs a guaranteed shape.
- **Constrained decoding** — enforcing that structure by masking illegal tokens at
  each generation step. Problem: "please respond in JSON" is unreliable; masking
  makes invalid output *impossible*.
- **Grammar / finite-state machine (FSM)** — the compiled schema that knows which
  tokens are legal next, given the state so far. Same idea as a regex engine.
- **Logits** — the model's raw per-token scores, before sampling. Where the mask is
  applied.
- **Logit masking** — setting illegal tokens' scores to −∞ before sampling, so only
  a legal token can be picked. The mechanism that enforces the grammar.
- **Strict-mode schema subset** — only the JSON-Schema features that compile to a
  grammar (types, `required`, `additionalProperties`, enums) — *not* numeric
  min/max. Why our `score` can't enforce 0–100 at the schema level.

## Evaluation

- **Golden set** — hand-verified question→answer (or question→page) pairs used as
  ground truth. Problem: you can't measure quality without a trusted answer key.
- **recall@k** — fraction of questions whose correct page is somewhere in the top-k
  retrieved. Measures: did we *fetch* the right thing?
- **precision@k** — fraction of the top-k that are actually relevant. Measures: how
  much of what we fetched is noise?
- **MRR (Mean Reciprocal Rank)** — average of `1/rank` of the first correct hit.
  Measures: how *high* did the right thing rank?
- **LLM-as-judge** — an LLM scores an answer against a reference. Problem:
  exact-match can't grade prose; a model can judge factual equivalence.
- **Cross-model judging** — the judge is a *different* model from the producer
  (GPT-4 grades Claude). Problem: a model grading its own homework is biased
  (ADR-0007).
- **Answer correctness** — does the answer match the reference facts? (What M4
  measures.)
- **Faithfulness / groundedness** — is every claim in the answer *supported by the
  retrieved context*? Problem: an answer can be factually right yet unsupported (a
  lucky guess); this catches the difference. Distinct from correctness.
- **RAGAS** — an open-source framework of LLM-computed RAG metrics (faithfulness,
  answer relevancy, context precision/recall). The off-the-shelf version of the
  evals we hand-rolled.

## Frontier / to-learn

- **Query expansion / multi-query** — rewrite or expand the question into several
  before retrieving. Problem: a single phrasing misses passages worded differently.
- **HyDE (Hypothetical Document Embeddings)** — embed a *hypothetical answer*
  instead of the question. Problem: questions and answers are worded differently; a
  drafted answer sits closer to the real passage in vector space.
- **Late interaction / ColBERT** — match at the token level instead of one vector
  per chunk. Problem: a single chunk vector blurs detail; token-level keeps it, at
  higher storage/compute cost.
- **Agentic tool use / function calling** — the LLM invokes tools via structured
  outputs. Problem: plain text can't take actions; a schema turns an intention into
  a callable function. (Same masking machinery as structured outputs.)
- **Document AI / layout-aware extraction / OCR** — parsing scanned or
  layout-heavy PDFs. Problem: naive text extraction garbles tables and columns and
  can't read images at all.

---

## Python & architecture (non-AI, for completeness)

- **Monkeypatch** — swapping a function/attribute at runtime in a test (≈ .NET Fakes
  shims). Problem: you want to test your logic without hitting a real API.
- **ADR (Architecture Decision Record)** — a short dated note capturing one
  decision and its trade-offs (Nygard format). Problem: the "why" behind a choice
  evaporates otherwise.
- **Ports & adapters / hexagonal** — isolate external services (LLM, DB) behind
  small adapter modules. Problem: swapping a provider shouldn't ripple through the
  core.
- **Screaming architecture** — the folder tree names the domain, not the framework,
  so the structure "screams" what the app does.

_This section can grow its own file if it gets long — for now it rides along._
