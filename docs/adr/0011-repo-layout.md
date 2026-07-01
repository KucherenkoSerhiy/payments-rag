# 0011 — Code in a nested `app/`, separate from the planning docs

**Status:** Accepted 2026-06-15

## Context
The project folder already held the planning docs (`scoping.md`,
`pet-project-roadmap.md`, `checklists.md`, `CLAUDE.md`). The actual code needed a
home that wouldn't intermingle with those instruction files.

## Decision
Put the real, git-tracked code repo in a nested `app/` subfolder. The planning
docs live one level up and are **not** part of the code repo.

## Alternatives
- **Code at the project root, alongside the docs.** Simpler path, but mixes
  human-facing planning prose with source, muddies `.gitignore`, and makes the
  repo's "this is the software" boundary fuzzy.

## Consequences
- Clean separation: `app/` is the portfolio repo you'd push to GitHub; the docs
  are private planning context.
- All tooling (uv, pytest, docker-compose paths) is rooted at `app/`, so commands
  run from there.
- ADRs live *inside* `app/docs/adr/` — they're about the software and ship with it.
