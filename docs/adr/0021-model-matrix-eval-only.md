# 0021 - Model-matrix experiment (multi-topic, multi-vendor), eval-only

**Status:** Accepted 2026-09-01 - authorizes a second comparison experiment
under `comparison/matrix/`, plus three new *eval-only* API providers (Google
Gemini, Voyage AI, DeepSeek). Does not reopen ADR-0004, and changes nothing
about production.

## Context

The vs-managed-rag comparison (ADR-0019, published as the two-part "Comparing
RAGs" article) varied the *framework* with models held constant. Its own
"Out of Scope" section named the two gaps: a small single-topic golden set,
and a single untested model combination. The owner decided to close both as a
follow-up experiment: same corpus-in/answer-out discipline, but now the
framework is frozen and the **models** are the only variables.

Two of the follow-up's needs collide with existing decisions if done naively:

* New vendors (Gemini, Voyage, DeepSeek) usually mean new SDK dependencies -
  but ADR-0004's "no frameworks, minimal deps" stance still applies.
* New topic corpora could contaminate the production index the way the stale
  fixture did (see docs/incidents/2026-08-29) - and their content (WHO fact
  sheets, GNU GPL FAQ, vendor guides) carries third-party licenses the repo
  must not republish.

## Decision

1. **One frozen pipeline, models as the only variables.** A hand-rolled
   chunk/embed/retrieve/generate pipeline in `comparison/matrix/` - 200-word
   chunks with 20-word overlap (the ADR-0019 standardization anchor), cosine
   top-5, one shared answer prompt. 6 embedder/generator pipelines; every
   pipeline differs from some other by exactly one component, except the one
   explicitly flagged `cross_stack` (Google-native, whole-stack comparison
   only). Tests encode both invariants.

2. **Four topics, 20 questions each** - sepa (10 verbatim from the ADR-0019
   golden set for cross-experiment comparability + 10 new), open-source
   licenses, agentic workflows, nutrition myths. Corpus content is fetched
   and converted locally by scripts and **never committed** (extends the
   existing corpus policy in .gitignore); the production pgvector DB is never
   touched - matrix retrieval is in-memory only.

3. **Three judges, every answer scored by all three** (Claude, GPT, Gemini -
   one per vendor family) with an identical plain-JSON rubric and no
   vendor-specific structured output. Same-family judge/generator cells are
   the self-preference-bias measurement; cross-family cells are the ADR-0007
   score. Judge scores are never averaged across judges.

4. **No new Python dependencies.** DeepSeek and Gemini are called through
   their OpenAI-compatible endpoints with the existing `openai` SDK; Voyage
   through its plain REST API with the already-present `httpx`. The three new
   API keys are eval-only, optional (missing keys skip their pipelines
   loudly), and documented in `.env.example`.

## Consequences

* Three new companies receive corpus data during eval runs - acceptable for
  these corpora (public documents), and itself a talking point for the
  article series' data-exposure thesis. Production traffic still goes only
  to Anthropic + OpenAI.
* Golden sets are DRAFT until owner review; nothing scored against them is
  citable before that.
* Price constants in `comparison/matrix/config.py` are snapshots and must be
  re-verified against vendor pricing pages before publication.
