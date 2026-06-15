# Payments RAG Agent

A retrieval-augmented agent for payments engineers. Ask a natural-language
question about **SEPA SCT, SCT Inst, or pacs.\* (ISO 20022)** messages; get a
short answer with clickable citations to the spec passages that support it.

> The LLM can be wrong. Always navigate to the cited source before trusting an
> answer. See `../scoping.md` for the full contract, goals, and non-goals.

This folder is the actual code repo. The planning docs (`scoping.md`,
`pet-project-roadmap.md`, `checklists.md`, `CLAUDE.md`) live one level up and are
kept separate from the code on purpose.

## Status: Week 1 spike

Proving every external integration before building the real pipeline. The four
spike scripts under `spike/` each prove one thing:

| Step | Proves | Command |
|---|---|---|
| 1 | Postgres + pgvector up, SQL/vector session works | `uv run python -m spike.step1_db` |
| 2 | One raw Claude API call | `uv run python -m spike.step2_llm` |
| 3 | Embed → store in pgvector → retrieve nearest neighbour | `uv run python -m spike.step3_embed` |
| 4 | One SEPA PDF page → extract → chunk → embed → store → retrieve | `uv run python -m spike.step4_pdf <pdf>` |

## Setup

Prereqs: Docker, and [`uv`](https://docs.astral.sh/uv/).

```bash
# 1. Configure secrets
cp .env.example .env        # then fill in ANTHROPIC_API_KEY + OPENAI_API_KEY

# 2. Start the vector store (Postgres + pgvector on host port 5433)
docker compose -f infra/docker-compose.yml up -d

# 3. Install dependencies
uv sync

# 4. Run the spike
uv run python -m spike.step1_db
uv run python -m spike.step2_llm
uv run python -m spike.step3_embed
# step 4 needs a real PDF — drop one in corpus/raw/ first:
uv run python -m spike.step4_pdf corpus/raw/your-sepa-spec.pdf 1 -- "what does this page cover?"
```

## Tests

```bash
uv run pytest          # unit tests (chunker) — fast, no API/DB
```

## Tech stack (locked in scoping.md — don't add deps without asking)

- Python 3.12+ via `uv`
- LLM: Claude Haiku 4.5 via API (raw SDK, no LangChain/LangGraph). Scoping doc names 3.5 Sonnet; swapped to Haiku for cost.
- Embeddings: OpenAI `text-embedding-3-small` (pinned — changing it re-embeds everything)
- Vector store: Postgres + `pgvector` in Docker
- Citations: structured JSON (later milestone)

## Layout

```
payments_rag/      shared library: config, db, embedding, chunker
spike/             W1 integration proofs (step1..step4)
infra/             docker-compose.yml + init.sql (chunks table, vector index)
corpus/raw/        SEPA / ISO 20022 source PDFs (gitignored)
corpus/processed/  derived chunks (gitignored)
tests/             unit tests
```
