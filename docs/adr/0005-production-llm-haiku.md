# 0005 — Production LLM: Claude Haiku 4.5

**Status:** Accepted 2026-06-15 — **supersedes** scoping v1's "Claude 3.5 Sonnet"

## Context
Scoping v1 named Claude 3.5 Sonnet as the production responder. By 2026-06 that
model (`claude-3-5-sonnet-20241022`) was **retired** — it would 404. A model
choice was needed that is current and cost-appropriate for a pet project.

## Decision
Use **Claude Haiku 4.5** (`claude-haiku-4-5`, $1/$5 per 1M tokens) as the
production responder. `LLM_MODEL` is env-configurable so the model is a knob, not
a hardcode.

## Alternatives
- **Claude Sonnet 4.6** ($3/$15). Higher quality on dense ISO 20022 text; ~3×
  cost. Kept as the A/B partner — swap `LLM_MODEL` and re-run the eval.
- Staying on 3.5 Sonnet: impossible (retired).

## Consequences
- ~3× cheaper generation; fine for a demo and eval iteration.
- Haiku is the weakest current Claude tier — likely lower accuracy on the ≥95%
  goal than Sonnet. Accepted because the model is a config swap and the eval will
  quantify the trade-off (don't guess, measure).
- The eval **judge** must stay a *different* model (GPT-4) — see [0007](0007-cross-model-llm-judge.md).
- `scoping.md` carries a reconciliation note; the contract's rationale is
  otherwise unchanged (same vendor, same role).
