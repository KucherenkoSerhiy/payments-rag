# 0013 - Deployment: Docker, local only (no hosted service)

**Status:** Accepted (2026-06, scoping v1)

## Context
The project needs to be reproducible by anyone reviewing it, but it is a
single-user demo, not a product.

## Decision
Ship the vector store via `docker-compose`; run the app locally. No hosted
endpoint. Anyone clones the repo, sets keys, `docker compose up`, and runs it.

## Alternatives
- **Hosted deploy** (Fly.io, Railway, Vercel). Gives a live demo URL, but adds
  cost, ops burden, and secret management, plus a moving target to maintain.

## Consequences
- No public demo URL; reviewers reproduce locally instead (sufficient for V1).
- No multi-user, auth, or uptime concerns to build.
- Keys live in a local, gitignored `.env`, plaintext on disk, so don't share the
  folder. A hosted deploy would force a real secrets story (a Phase-2 concern).
