# Deploying payments-rag to the public internet

This walks you from a fresh clone to a live URL in under 30 minutes. Target
stack: Fly.io for the app container, Neon for Postgres + pgvector, Cloudflare
as an optional edge layer. Cost at expected traffic (~10 visits/day): under
$5/month for infrastructure, plus capped LLM spend of at most $9/month.
Background and trade-offs live in [architecture.md](architecture.md) and
[ADR-0018](../docs/adr/0018-cloud-deploy-fly-neon.md).

## What you need before starting

- Docker running locally (the seed script uses the local pgvector container's
  psql, and the app deploys as a Docker image).
- A [Fly.io](https://fly.io) account with a payment method (no free tier since
  2024; the app costs about $2/month) and the
  [flyctl CLI](https://fly.io/docs/flyctl/install/) installed.
- A [Neon](https://neon.com) account. The free plan is plenty: the corpus is
  484 chunks, well under the 0.5 GB storage cap.
- Anthropic and OpenAI API keys with a small prepaid balance.
- The rulebook PDFs in `corpus/raw/` (gitignored; see the main README for
  where to download them). Skip this if you only want the copy-based seed and
  don't care about PDF deep links. The Docker image bundles whatever is in
  `corpus/raw/` at build time.

## 1. Create the database on Neon

1. In the Neon console, create a project. Pick a region near your Fly region
   (Frankfurt pairs fine with Madrid).
2. Copy the **direct** connection string (not the pooled one; the app opens
   short-lived connections and pgvector type registration prefers a real
   Postgres endpoint). It looks like
   `postgresql://user:pass@ep-xxx.eu-central-1.aws.neon.tech/neondb?sslmode=require`
3. Export it for the next steps: `export NEON_URL='postgresql://...'`

## 2. Apply the schema and seed the chunks

From the repo root, with the local docker DB running (`make db`):

```bash
./deploy/seed-neon.sh schema "$NEON_URL"
./deploy/seed-neon.sh copy   "$NEON_URL"    # free: copies local chunks as-is
./deploy/seed-neon.sh verify "$NEON_URL"    # expect: 484 chunks, 3 sources
```

No local DB with indexed chunks? Use `index` instead of `copy`. It re-embeds
the PDFs in `corpus/raw/` against Neon directly and costs pennies (ADR-0003):

```bash
DATABASE_URL="$NEON_URL" OPENAI_API_KEY=sk-... ./deploy/seed-neon.sh index "$NEON_URL"
```

## 3. Create and deploy the Fly app

From the repo root:

```bash
fly auth login
fly apps create payments-rag        # pick another name if taken; update deploy/fly.toml
fly secrets set -c deploy/fly.toml \
    ANTHROPIC_API_KEY='sk-ant-...' \
    OPENAI_API_KEY='sk-...' \
    DATABASE_URL="$NEON_URL"
fly deploy -c deploy/fly.toml
```

The first deploy builds the image remotely (Node builds the Angular SPA,
Python installs via uv) and boots one 256 MB shared-CPU machine. It stops
itself when idle and wakes on the next request; a cold start takes a few
seconds, which is fine for a demo.

## 4. Verify it works

```bash
curl https://payments-rag.fly.dev/healthz          # {"ok":true} and no paid calls
curl -X POST https://payments-rag.fly.dev/ask \
     -H 'Content-Type: application/json' \
     -d '{"question":"How fast must an SCT Inst payment be settled?"}'
```

Then open https://payments-rag.fly.dev in a browser: the Ask tab should answer
with clickable page citations, and Evals, Usage, and Health should load.

Check the wallet guard too, since it is the only thing between the public
internet and your API balance:

- Rate limit: send 21 asks within an hour from one machine; the 21st gets 429
  with a Retry-After header.
- Budget cap: set a tiny cap with `fly secrets set DAILY_BUDGET_USD=0.001`,
  ask twice, expect the "come back tomorrow" message, then restore it with
  `fly secrets unset DAILY_BUDGET_USD` (the fly.toml default takes over).

## 5. Cloudflare (optional, needs a custom domain)

The `.fly.dev` URL works as-is. Cloudflare's free tier adds edge caching, bot
filtering, and a second rate-limit layer, but only for a domain whose
nameservers point at Cloudflare:

1. Add your domain to Cloudflare (free plan), point a CNAME at
   `payments-rag.fly.dev`, keep the proxy (orange cloud) on.
2. `fly certs add yourdomain.example` so Fly serves TLS for it.
3. Add one rate-limiting rule (free plan includes one): path `/ask`,
   method POST, threshold 30 requests per minute per IP, action block. This
   sits above the app's own 20/hour limit and absorbs floods before they
   reach (and wake) the machine.

No domain? Skip this. The app-level guards carry the protection on their own.

## Costs, and what to do when they drift

See [architecture.md](architecture.md) for the full breakdown and the swap
plan per provider. Short version: Fly ~$2, Neon $0, Cloudflare $0, LLM spend
hard-capped at $0.30/day by the wallet guard. Check `fly dashboard` billing
and the Neon console usage page once a week for the first month.

## Troubleshooting

- **`fly deploy` can't find the Dockerfile**: run from the repo root and pass
  `--dockerfile deploy/Dockerfile.prod` explicitly.
- **App boots but /ask fails with a DB error**: the DATABASE_URL secret is
  missing `?sslmode=require`, or points at the pooled endpoint. Use the direct
  string from step 1.
- **429 on everything**: the daily budget tripped (look for "daily budget
  reached" in `fly logs`). It resets at midnight UTC, or raise
  DAILY_BUDGET_USD in deploy/fly.toml and redeploy.
- **OOM or restarts under load**: bump `memory = "512mb"` in deploy/fly.toml
  (~$2/month more).
- **PDF links 404**: the image was built without `corpus/raw/` PDFs. Download
  them (main README), rebuild, redeploy.
