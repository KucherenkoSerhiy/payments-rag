#!/usr/bin/env bash
# Seed the deployed Postgres (Neon) with the schema and the rulebook chunks.
#
# Usage (Git Bash on Windows works; docker must be running):
#   ./deploy/seed-neon.sh schema  "$NEON_URL"   # apply infra/init.sql
#   ./deploy/seed-neon.sh copy    "$NEON_URL"   # copy chunks from the local docker DB (free)
#   ./deploy/seed-neon.sh index   "$NEON_URL"   # re-embed corpus/raw PDFs (costs pennies)
#   ./deploy/seed-neon.sh verify  "$NEON_URL"   # count chunks + smoke-query
#
# NEON_URL is the direct (non-pooled) connection string, e.g.
#   postgresql://user:pass@ep-xxx.eu-central-1.aws.neon.tech/neondb?sslmode=require
#
# "copy" preserves the exact chunk ids and vectors from the local DB, so it is
# the default path. "index" is the fallback when there is no local DB (fresh
# clone): it needs OPENAI_API_KEY and the PDFs in corpus/raw.
#
# psql/pg_dump run inside the local pgvector container so nothing needs to be
# installed on the host.

set -euo pipefail

MODE="${1:?mode required: schema | copy | index | verify}"
URL="${2:?Neon connection string required}"
CONTAINER="payments_rag_db"
cd "$(dirname "$0")/.."

case "$MODE" in
  schema)
    docker exec -i "$CONTAINER" psql "$URL" -v ON_ERROR_STOP=1 < infra/init.sql
    echo "schema applied"
    ;;
  copy)
    echo "dumping chunks from local $CONTAINER and restoring to Neon..."
    # TRUNCATE first so a re-run (e.g. after a half-finished attempt) is
    # idempotent instead of dying on duplicate ids mid-stream.
    docker exec "$CONTAINER" psql "$URL" -v ON_ERROR_STOP=1 -c "TRUNCATE chunks;"
    docker exec "$CONTAINER" pg_dump -U payments -d payments_rag \
        --data-only --table=chunks \
      | docker exec -i "$CONTAINER" psql "$URL" -v ON_ERROR_STOP=1
    docker exec "$CONTAINER" psql "$URL" -v ON_ERROR_STOP=1 \
        -c "SELECT setval('chunks_id_seq', (SELECT coalesce(max(id), 1) FROM chunks));"
    echo "copy done"
    ;;
  index)
    # uv run resolves the project venv; bare `python` may be a system one
    # without the project's dependencies. Needs OPENAI_API_KEY in the env.
    DATABASE_URL="$URL" uv run python -m payments_rag.cli index --reset
    ;;
  verify)
    docker exec "$CONTAINER" psql "$URL" -t \
        -c "SELECT count(*) || ' chunks, ' || count(DISTINCT source) || ' sources' FROM chunks;" \
        -c "SELECT count(*) || ' wallet_guard rows' FROM wallet_guard;"
    ;;
  *)
    echo "unknown mode: $MODE (want schema | copy | index | verify)" >&2
    exit 1
    ;;
esac
