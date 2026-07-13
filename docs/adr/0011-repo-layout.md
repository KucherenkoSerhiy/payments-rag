# 0011 - Code in its own repository

**Status:** Accepted 2026-06-15

## Context
This project was developed alongside separate planning notes. The source needed a
home that wouldn't intermingle with that non-code material.

## Decision
Keep the code in its own self-contained git repository (this one), separate from
the planning notes.

## Consequences
- This repo is standalone software; the design rationale for the *code* lives in
  the other ADRs, which ship with it.
- All tooling (uv, pytest, docker-compose) is rooted at the repo, so commands run
  from the repo root.
