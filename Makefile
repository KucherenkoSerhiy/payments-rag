# Payments RAG - common tasks. Run `make help` for the list.
#
# Setup uses uv (the repo ships a uv.lock): `make install`, then activate the venv
# it creates. Every other target calls `python` directly, so an activated venv
# works as-is; point elsewhere with e.g. `make api PYTHON=.venv/Scripts/python.exe`.

PYTHON  ?= python
COMPOSE := docker compose -f infra/docker-compose.yml

.PHONY: help install db down index api ui test smoke

help:  ## list the targets
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*## "}{printf "  %-8s %s\n", $$1, $$2}'

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
