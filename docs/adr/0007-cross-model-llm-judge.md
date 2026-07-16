# 0007 - Eval scoring: cross-model LLM-as-judge

**Status:** Accepted 2026-06 - implemented

## Context
Accuracy on the golden set is the project's headline metric. Answers are free
text, so scoring needs to tolerate paraphrase while still catching factual error.

## Decision
Score with an LLM-as-judge, and require the judge to be a **different model** from
the production responder (e.g. Haiku produces, GPT-4 judges). The judge receives
`(question, expected, actual)` and returns a 0-100 grade + critique.

## Alternatives
- **Exact-text match**: fails on paraphrase.
- **Semantic similarity (embedding distance)**: too lenient on factual errors
  (wrong-but-similar scores high).
- **Same-model judge**: shares the producer's blind spots; it's marking its own
  homework.

## Consequences
- A second LLM dependency and per-eval cost, capped by running the full golden
  set weekly rather than per-PR.
- Requires two capable models from different vendors (Anthropic + OpenAI), which
  the project already uses.
- Judge quality is itself a risk, so grade a sample by hand periodically to keep
  the judge honest.
