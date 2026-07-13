# 0017 - Frontend: Angular SPA + FastAPI backend (supersedes ADR-0010)

**Status:** Accepted 2026-07-11 - supersedes ADR-0010 (minimal Streamlit UI).

## Context
ADR-0010 chose Streamlit for a minimal UI "to see retrieval." It over-delivered:
we now have a three-view glass-box app (Ask / Evals / Usage + a Health panel) that
is measured and observable (see `docs/writeups/ui-current-state-streamlit.md`). It
was the right call for discovering what to build, and it even caught real bugs
in-browser (the ~10s localhost DB hang, a cwd-relative path).

But three forces now point past it:
1. **Design ceiling.** The target UX (top nav with role-labeled tabs, a search
   hero, inline citation chips that link to evidence, a live multi-dependency
   Health view) needs a real frontend. Streamlit can't render it (we confirmed
   `st.navigation(position="top")` doesn't even produce a top bar here).
2. **Cloud deploy (M8) needs an API layer anyway.** A FastAPI backend isn't extra
   work relative to the roadmap; it's work M8 requires regardless.
3. **Skill fit.** The owner is a .NET/Angular engineer. Angular plays to existing
   strength for the presentation layer while Python stays the learning core.

## Decision
Rebuild the frontend as an **Angular SPA** over a **FastAPI backend** that exposes
the existing Python core (`orchestrator.answer`, retrieval/answer evals, the query
log, and a new multi-dependency health module) as HTTP endpoints. The mockups
(2026-07-11) are the design spec. Streamlit is retired once the new UI reaches
parity, or kept only as an internal dev quick-view.

## Alternatives
- **Keep Streamlit + custom CSS.** Rejected: the ceiling is structural (nav,
  routing, inline interactivity), not cosmetic.
- **Another Python UI** (Reflex / NiceGUI / Gradio). Rejected: still doesn't give
  the control we want, and doesn't play to the owner's Angular strength.
- **Server-rendered templates.** Rejected: an SPA fits an interactive Q&A tool
  better, and the API is reusable.

## Consequences / trade-offs
- **+** An API layer decouples the core from any UI and is exactly what M8 needs.
- **+** The real UX becomes possible (inline citations, live health, top nav).
- **+** Plays to the owner's strength; the mockups are a ready spec.
- **−** More work than restyling Streamlit; two runtimes (Python API + Node/Angular).
- **−** A parity migration: reproduce the four views' behavior against the API.
- The **Python core is unchanged**: orchestrator, retrieval, evals, `query_log`
  stay as-is. Only the presentation + a thin API layer are new. ADR-0010 remains in
  history; its context was correct at the time.

## Migration path
1. **FastAPI backend** first, with endpoints for `ask`, `evals` (retrieval + answer,
   with run duration), `usage`, and `health` (per-dependency + all). Verifiable via
   `curl`/httpx before any frontend exists.
2. **Angular app** consuming it, view by view, against the mockups.
3. **Retire Streamlit** at parity.
