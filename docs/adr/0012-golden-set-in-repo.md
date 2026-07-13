# 0012 - Golden eval set: YAML file in the repo

**Status:** Accepted 2026-06 - built

## Context
The eval suite replays a curated set of questions with expected answers. That set
*is* the ground truth; the accuracy number is only as good as it.

## Decision
Keep the golden set as a YAML (or JSON) file in the repo.

## Alternatives
- **A database or external eval service.** Adds infra and setup; can't be
  reviewed in a PR.

## Consequences
- Version-controlled and diff-able: adding a failing case is "add a line, commit."
- Reviewable in PRs: changes to the ground truth are visible, which guards
  against quietly editing the set to chase the number (the overfitting risk).
- Runs anywhere with no DB setup.
- Single-author only (no concurrent editing), a non-issue for a solo project.
