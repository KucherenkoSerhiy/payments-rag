# Payments RAG - common tasks. Run `make help` for the list.
#
# Setup uses uv (the repo ships a uv.lock): `make install`, then activate the venv
# it creates. Every other target calls `python` directly, so an activated venv
# works as-is; point elsewhere with e.g. `make api PYTHON=.venv/Scripts/python.exe`.

PYTHON  ?= python
COMPOSE := docker compose -f infra/docker-compose.yml

.PHONY: help install db down index api ui test smoke \
        compare-payments-rag compare-openai compare-notebooklm compare-haystack compare-llamaindex compare-langchain \
        compare-score compare-judge compare-all

help:  ## list the targets
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*## "}{printf "  %-22s %s\n", $$1, $$2}'

install:  ## sync Python dependencies (uv)
	uv sync

db:  ## start Postgres + pgvector in Docker
	$(COMPOSE) up -d

down:  ## stop the database
	$(COMPOSE) down

index:  ## index the PDFs in corpus/raw
	$(PYTHON) -m payments_rag.cli index --reset

api:  ## run the FastAPI backend on http://127.0.0.1:8000
	$(PYTHON) -m uvicorn api.main:app --reload

ui:  ## run the Angular dev server on http://localhost:4200
	cd frontend && npm install && npm start

test:  ## ruff + pytest
	$(PYTHON) -m ruff check . && $(PYTHON) -m pytest -q

smoke:  ## end-to-end: index a sample PDF, answer a question, expect a citation
	$(PYTHON) -m pytest tests/test_smoke.py -q

# --- vs-managed-rag comparison (docs/vs-managed-rag.md) ---
# Two-phase by necessity: collection needs this project's own deps (openai>=2,
# psycopg, anthropic); RAGAS scoring needs langchain, which this project does
# NOT depend on (ADR-0004) and never will as a real dependency (see
# evals/ragas_metrics.py). `compare-score` runs it in a throwaway `uv --isolated`
# environment instead, so it never touches pyproject.toml or uv.lock.
RAGAS_ISOLATED := uv run --isolated --with "ragas==0.4.3" --with "langchain-community<0.3" \
                  --with langchain-openai --with python-dotenv

compare-payments-rag:  ## comparison: collect payments-rag's own answers on the golden set
	PYTHONIOENCODING=utf-8 PYTHONPATH=. $(PYTHON) -m comparison.collect.payments_rag

compare-openai:  ## comparison: collect OpenAI file_search's answers (real cost, ~$0.35/run)
	PYTHONIOENCODING=utf-8 PYTHONPATH=. $(PYTHON) -m comparison.collect.openai_filesearch

compare-notebooklm:  ## comparison: replay NotebookLM's manually-gathered answers (see comparison/collect/notebooklm.py docstring)
	PYTHONIOENCODING=utf-8 PYTHONPATH=. $(PYTHON) -m comparison.collect.notebooklm

compare-haystack:  ## comparison: collect answers from a Haystack-built RAG pipeline (isolated env, see docs/adr/0019)
	PYTHONPATH=. PYTHONIOENCODING=utf-8 uv run --isolated --with haystack-ai --with nltk --with python-dotenv --with pyyaml \
		python -m comparison.collect.framework haystack

compare-llamaindex:  ## comparison: collect answers from a LlamaIndex-built RAG pipeline (isolated env, see docs/adr/0019)
	PYTHONPATH=. PYTHONIOENCODING=utf-8 uv run --isolated --with llama-index --with llama-index-embeddings-openai \
		--with llama-index-llms-openai --with pypdf --with python-dotenv --with pyyaml \
		python -m comparison.collect.framework llamaindex

compare-langchain:  ## comparison: collect answers from a LangChain/LangGraph-built RAG pipeline (isolated env, see docs/adr/0019)
	PYTHONPATH=. PYTHONIOENCODING=utf-8 uv run --isolated --with langgraph --with langchain-openai \
		--with langchain-text-splitters --with pypdf --with tiktoken --with python-dotenv --with pyyaml \
		python -m comparison.collect.framework langchain

compare-score:  ## comparison: score every collected system with RAGAS (isolated env; resumes from cached rows, skips systems with no data yet)
	PYTHONPATH=. PYTHONIOENCODING=utf-8 $(RAGAS_ISOLATED) python -m comparison.score_comparison

compare-judge:  ## comparison: grade every collected system with the cross-model judge (evals/judge.py), no isolation needed
	PYTHONPATH=. PYTHONIOENCODING=utf-8 $(PYTHON) -m comparison.judge_comparison

compare-all: compare-payments-rag compare-openai compare-notebooklm compare-haystack compare-llamaindex compare-langchain compare-score compare-judge  ## comparison: run every system + both scorers
