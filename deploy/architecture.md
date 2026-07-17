# Deployed architecture

One page: what runs where, what it costs, and how to swap any part that gets
expensive. The decision record is
[ADR-0018](../docs/adr/0018-cloud-deploy-fly-neon.md).

## Topology

```
                       (optional, custom domain only)
  visitor ──HTTPS──▶  Cloudflare edge: cache, bot filter, rate rule
                          │
                          ▼
                      Fly.io, region mad
                      one shared-cpu-1x machine, 256 MB, scale-to-zero
                      ┌─────────────────────────────────────────┐
                      │ uvicorn :8080                           │
                      │  ├─ FastAPI api/ (ask, evals, usage,    │
                      │  │   health, source PDFs)               │
                      │  ├─ wallet guard (api/guard.py)         │
                      │  └─ static Angular SPA (same origin)    │
                      └───────┬─────────────┬───────────────────┘
                              │             │
                    TLS 5432  ▼             ▼  HTTPS
                      Neon Postgres      Anthropic (Haiku 4.5, answers)
                      + pgvector         OpenAI (embeddings + judge)
                      484 chunks
                      wallet_guard ledger
```

One container serves both the API and the built SPA. That kills the CORS
problem and the second host: the frontend calls relative URLs on its own
origin. The Angular dev server setup (4200 -> 8000) still works unchanged.

The machine stops when idle and wakes on the next request in a few seconds.
At ~10 visits/day it sleeps most of the time, which is where the low bill
comes from. Fly's health check hits `/healthz`, which is free; the full
`/health` view makes paid 1-token pings and is budget-gated like the rest.

## State, and what survives what

| State | Where | Survives redeploy? |
|---|---|---|
| Chunks + embeddings | Neon `chunks` table | yes |
| Daily API spend ledger | Neon `wallet_guard` table | yes |
| Rate-limit counters | app memory | no (by design; cap is the backstop) |
| Query log / Usage tab | `data/queries.jsonl` in the container | no |

The query log resetting on redeploy is a known, accepted limitation for the
demo. If it starts to matter, the fix is a small table in Neon next to
wallet_guard, not a volume.

## Cost breakdown (monthly, expected traffic)

| Component | Plan | Expected | Worst case |
|---|---|---|---|
| Fly.io machine | shared-cpu-1x, 256 MB, scale-to-zero | ~$2 | ~$3 (always-on) |
| Fly bandwidth | ~100 MB/mo | ~$0 | $1 |
| Neon Postgres | free plan (0.5 GB, 100 compute-hrs) | $0 | $0, then upgrade signal |
| Cloudflare | free plan | $0 | $0 |
| Anthropic + OpenAI | hard-capped by wallet guard | ~$1 | $9 ($0.30/day cap) |
| **Total** | | **~$3** | **~$13** |

A measured ask costs about $0.0015 (Haiku in/out tokens plus one embedding),
so the $0.30 daily cap is roughly 200 questions. The cap is enforced in the
app against the `wallet_guard` ledger, so it holds even across restarts. It
does not cover local eval runs from a dev machine; those spend from the same
keys, so keep the prepaid balance small.

## Swapping a provider

Each component talks to its neighbors through one narrow interface, so swaps
stay local:

- **Fly.io -> Railway or Render.** The image is a plain Dockerfile listening
  on 8080 with env-var config. Point the new platform at
  `deploy/Dockerfile.prod`, set the same three secrets, keep the port. Only
  `fly.toml` is Fly-specific.
- **Neon -> Supabase or any Postgres with pgvector.** The app only needs a
  `DATABASE_URL`. Re-run `deploy/seed-neon.sh schema` + `copy` against the
  new instance; the seed script only assumes psql reaches it.
- **Cloudflare -> nothing.** It is optional; removing it removes an
  optimization, not a capability.
- **The LLM and embedding model are not swappable here.** ADR-0005 and
  ADR-0003 lock them; the embedding dimension (1536) is baked into the
  schema.

## Failure modes to know about

- Neon free-tier compute hours exhausted: DB refuses connections until the
  month rolls over. /healthz stays green (it is DB-free), /ask fails loudly.
  Fix: upgrade Neon or accept the outage; the free 100 hours are far above
  what 10 visits/day consume.
- Budget cap tripped: every paid endpoint answers 429 with a friendly note
  until midnight UTC. This is working as intended, not an outage.
- Cold start after idle: first request takes a few seconds longer. Accepted
  for a demo; `min_machines_running = 1` removes it for ~$1/month more.
