# 0010 - UI: minimal Streamlit

**Status:** Superseded by [ADR-0017](0017-frontend-angular-fastapi.md) (2026-07-05)

The Streamlit UI here was retired in M7; an Angular SPA over a FastAPI backend
replaced it. This ADR is kept as history. The reasoning below is why Streamlit
was chosen first; it is not a description of the current UI.

## Context
Running retrieval from the CLI (`cli query "..."`) works but is clumsy for
exploration. A query box makes poking the system far easier. Scoping lists the UI
as a Phase-2 concern and names Streamlit *or* FastAPI+HTML as the options.

## Decision
Add a minimal **Streamlit** app (`ui/streamlit_app.py`): a question box, a top-k
slider, and the retrieved passages with source/page/distance. Retrieval only,
no generated answers yet.

## Alternatives
- **FastAPI + tiny HTML**: more control, more code; overkill for a dev tool.
- **React / Next.js**: explicitly a non-goal; the UI is not the differentiator.
- **CLI only**: no extra dep, but poor for interactive exploration.

## Consequences
- Adds the `streamlit` dependency (~app tier, scoping-approved).
- Built slightly *ahead* of the roadmap (UI is Phase 2). This is a conscious
  deviation, justified because "query is the checkpoint" and a box beats a
  terminal. Flagged as such, not smuggled in.
- The answer layer (Week 3) slots into the same page later; today it's a pure
  retrieval demo, honest about showing passages, not answers.
