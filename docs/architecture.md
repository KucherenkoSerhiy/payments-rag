# Architecture

Three independent paths, each running at a different time. Solid = built today;
dashed/"planned" = Week 3+.

## Module map

The package is grouped by concern so the folder tree mirrors the architecture
(ADR-0015): `indexing/`, `retrieval/`, `adapters/`, plus the `orchestrator`.

```
cli.py / ui/streamlit_app.py / smoke_test.py   entry points
        │
        ├── orchestrator.py     answer flow: retrieve → prompt → LLM → cited answer
        │
        ├── indexing/           offline: PDF → clean → chunk → embed → store
        │      ├── indexer.py     CorpusIndexer (the pipeline)
        │      ├── textprep.py    pure: strip repeated header/footer boilerplate
        │      └── chunker.py     pure: sentence-aware split + overlap
        │
        ├── retrieval/          online: question → top-k chunks
        │      ├── retriever.py   vector + hybrid (RRF) retrieval
        │      └── fusion.py      pure: reciprocal rank fusion
        │
        └── adapters/           external services (Ports & Adapters)
               ├── db.py          Postgres + pgvector (KNN + full-text)
               ├── embedding.py   OpenAI text-embedding-3-small
               └── llm.py         Anthropic Claude → structured {answer, citations}

config.py   settings (models, DSN, API timeouts, lazy key validation)
infra/      docker-compose (Postgres+pgvector) + init.sql (schema + HNSW + FTS)
```

Dependencies point inward: entry points → orchestrator → indexing/retrieval →
adapters → config. Nothing in `adapters/` imports the flow layers, and nothing
in the library imports the entry points.

## Path 1 — Indexing (offline, when the corpus changes)

```mermaid
sequenceDiagram
    actor Dev
    participant CLI as cli.index
    participant IX as indexer
    participant TP as textprep
    participant CH as chunker
    participant EM as embedding
    participant OAI as OpenAI API
    participant DB as pgvector

    Dev->>CLI: index --reset
    CLI->>DB: clear_all()
    CLI->>IX: index_corpus(corpus/raw)
    loop each PDF
        IX->>IX: PdfReader → raw page texts
        IX->>TP: find_repeated_lines(pages)
        TP-->>IX: boilerplate set
        loop each page
            IX->>TP: clean_page(raw, boilerplate)
            IX->>CH: chunk_text(clean)
            CH-->>IX: sentence chunks
        end
        IX->>EM: embed(batch of 100 chunks)
        EM->>OAI: POST /embeddings
        OAI-->>EM: vectors (1536-d)
        EM-->>IX: vectors
        loop each chunk
            IX->>DB: insert_chunk(text, page, vector)
            Note over DB: dimension guard, then<br/>INSERT ... %s::vector
        end
    end
    IX-->>Dev: stats (docs, pages, chunks)
```

## Path 2 — Query / retrieval (online, per question) — built today

```mermaid
sequenceDiagram
    actor User
    participant UI as UI / CLI
    participant RT as retriever
    participant EM as embedding
    participant OAI as OpenAI API
    participant DB as pgvector

    User->>UI: "how fast does SCT Inst settle?"
    UI->>RT: retrieve(question, k=5)
    RT->>EM: embed_one(question)
    EM->>OAI: POST /embeddings
    OAI-->>EM: query vector
    EM-->>RT: query vector
    RT->>DB: nearest(qvec, k)
    Note over DB: ORDER BY embedding <=> %s::vector<br/>(cosine, HNSW index)
    DB-->>RT: top-k rows (id, source, text, page, distance)
    RT-->>UI: RetrievedChunk[]
    UI-->>User: passages + source/page/distance
```

## Path 3 — Answer generation + eval (PLANNED, Week 3)

```mermaid
sequenceDiagram
    actor User
    participant OR as orchestrator (planned)
    participant RT as retriever
    participant LLM as Claude Haiku 4.5
    participant J as Judge GPT-4 (eval only)

    User->>OR: question
    OR->>RT: retrieve(question, k)
    RT-->>OR: chunks
    OR->>LLM: prompt(question + tagged chunks + JSON schema)
    LLM-->>OR: {answer, citations:[chunk_id]}
    OR->>OR: map chunk_id → source/page
    OR-->>User: answer + clickable citations

    Note over J: Eval path (offline): replay golden set →<br/>Judge grades (question, expected, actual, citations)
```

## Architecture review — is it clear and explicit? Mostly yes.

**Strengths**
- Clean layering; the three paths share exactly one keystone (the embedding
  model) and one store, which is the correct RAG shape.
- Explicit seams: `retriever.retrieve`, `db.nearest`, `embedding.embed` are the
  swap points (e.g. change vector store, change model) — each isolated.
- Pure logic (`chunker`, `textprep`) is separated from I/O, so it's unit-tested.

**Gaps / things to watch (honest list)**
1. **No answer layer yet** — Path 3 is the intended next build. Retrieval is
   proven; generation + citations are not.
2. **No resilience on external calls** — no retry/timeout/circuit-breaker on the
   OpenAI/Anthropic calls. The ~13-min first-batch hang is the symptom. Scheduled
   for Week 4; until then a flaky API blocks the pipeline.
3. **No eval harness** — the single biggest gap for "proof it works" (see below).
   Retrieval quality is currently unmeasured beyond eyeballing.
4. **`nearest` searches the whole table** — no per-document/source filter. Fine
   now; a real need once you want "search only the SCT Inst rulebook."
5. **Minor cohesion nit** — embedding *batching* lives in the indexer, not in
   `embedding.py`. Defensible (the indexer owns throughput), but worth noting.
6. **Dead code** — `clean_page`'s `U+FFFD` replace is a no-op (the artifact was
   misdiagnosed; see ADR 0009). Harmless; remove when convenient.

No major structural flaw. The architecture is appropriately small and the
missing pieces are *known and sequenced*, not accidental.
