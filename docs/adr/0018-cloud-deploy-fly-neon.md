# 0018 - Public cloud deploy: Fly.io + Neon, no auth

**Status:** Accepted 2026-07-17 - **supersedes** [ADR-0013](0013-deploy-docker-local.md) (Docker, local only)

## Context

ADR-0013 kept the project local on purpose: a hosted deploy meant cost, ops
burden, and "a real secrets story", none of which V1 needed. That calculus
changed. The LinkedIn articles link to the repo, and a reader who can click a
URL and ask a question is worth more than one who has to clone, get API keys,
and run docker-compose. The owner asked for a public demo anyone can try,
capped at $20/month all-in.

Article 06 already worked out what a public, no-login deploy of a shared-corpus
RAG needs: access control on admin views, abuse and cost guards, privacy
hygiene. This deploy takes the abuse-and-cost part in full and deliberately
drops the auth part.

## Decision

- **Host the app on Fly.io**: one shared-cpu-1x machine (256 MB), built from
  `deploy/Dockerfile.prod`, scale-to-zero when idle. The container serves both
  the FastAPI backend and the built Angular SPA on one origin.
- **Host Postgres + pgvector on Neon** (free plan). Schema is the same
  `infra/init.sql`; chunks are copied from the local DB or re-indexed.
- **Cloudflare in front, only if a custom domain shows up.** The `.fly.dev`
  URL ships first; the edge layer is an optimization, not a dependency.
- **Everything is public, including Evals, Usage, and Health.** No accounts,
  no admin token. This deviates from article 06's "gate the admin views" on
  the owner's explicit call: it is a portfolio demo, the views are part of
  what is being shown off, and simplicity wins. The privacy consequence is
  contained by the Usage tab only ever showing the ephemeral in-container
  query log (it resets on every deploy), but questions still travel to
  third-party LLM APIs, which the UI should state plainly.
- **Wallet protection is mandatory and lives in the app** (`api/guard.py`):
  per-IP rate limit on the paid endpoints, a global daily budget cap
  persisted in the `wallet_guard` table (hard 429 once spent), and an input
  length bound. Secrets move from the local `.env` to Fly secrets, which is
  the "real secrets story" ADR-0013 deferred.

## Alternatives

- **Stay local (keep ADR-0013).** Zero cost, zero risk, but article
  click-throughs land on a README instead of a working demo.
- **Railway or Render instead of Fly.** Comparable price and also fine; Fly
  won on scale-to-zero maturity and per-second billing. The Dockerfile is
  portable, so this choice is cheap to revisit (see deploy/architecture.md).
- **Supabase instead of Neon.** Also has pgvector on a free tier. Neon's
  scale-to-zero Postgres and plain connection string fit a single-table app
  better; Supabase brings an app platform this project doesn't need.
- **Add auth for the admin tabs** (article 06's original position). Rejected
  by the owner for this deploy: every gate costs demo-ability, and there is
  nothing behind the tabs worth a login while the query log is ephemeral.

## Consequences

- There is a live URL to maintain, and a monthly bill (~$3 expected, ~$13
  hard ceiling with the $0.30/day API cap; breakdown in
  deploy/architecture.md).
- The public can spend the owner's API money, bounded by the wallet guard.
  The guard is now load-bearing; its tests matter more than most.
- Anyone can run the Evals tab. That is a feature (the point is showing the
  eval discipline) and a cost, which is why evals sit behind their own rate
  limit and the shared budget cap.
- The query log and Usage tab reset on every deploy. Accepted for a demo;
  moving the log to a Neon table is the fix if it starts to matter.
- ADR-0013's local flow still works unchanged for development; this ADR adds
  a deploy target, it does not remove the local one.
