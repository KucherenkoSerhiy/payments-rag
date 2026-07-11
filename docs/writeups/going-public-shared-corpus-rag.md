# Going public with a shared-corpus RAG: users, access, privacy, cost

**TL;DR** — When a RAG serves *one shared, public corpus* (not per-user
documents), the hardest part of "multi-user" — data isolation — simply doesn't
apply. What a public deploy actually needs isn't accounts; it's **access control,
data privacy, and abuse/cost control**. Real accounts become a clean *future* add
at the API boundary, if personalization is ever wanted.

## The reframe: "multi-user" is really four questions

"Should it support multiple users?" bundles four very different concerns that have
very different answers for this app:

| Concern | Applies here? | Why | Mitigation |
|---|---|---|---|
| **Data isolation / tenancy** | **No** | Shared, public corpus; no per-user documents | — (revisit only if user uploads are added) |
| **Access control** | **Yes** | Admin/ops views (Evals, Usage, Health) aren't for the public | Gate those routes: admin token / basic-auth |
| **Data privacy** | **Yes** | The query log stores + displays everyone's questions; questions also go to third-party LLM APIs | Gate/anonymize the log, set retention, add a privacy note |
| **Abuse & cost** | **Yes** | Public + paid-per-call | Per-IP rate limit + global daily budget cap |
| **Accounts / identity** | **Deferred** | No personalization or quotas in scope | Add at the API layer if ever needed |

## Why the shared corpus changes everything

In a typical multi-tenant RAG, each user uploads *their own* documents, and the
cardinal rule is: never let one tenant's data surface in another tenant's answer.
That data-isolation requirement drives most of the complexity — separate indexes
or row-level filters, per-tenant keys, careful retrieval scoping.

Here, the corpus is the **public SEPA rulebooks — identical for every user**, and
there is no upload path. So everyone queries the same pgvector table, and there is
nothing to isolate. The hardest ~80% of multi-tenant RAG evaporates. This app is
"many readers, one shared knowledge base," not "each tenant's private vault."

## What a public deploy *actually* needs (no accounts required)

1. **Access control on the admin views.** The four tabs have different audiences:
   *Ask* is for the public; *Evals / Usage / Health* are developer/admin/ops.
   `Usage` in particular *shows every question everyone asked*. Put a shared admin
   token or basic-auth in front of those routes. This is "who sees which tab" — not
   identity.
2. **Abuse & cost guards.** Public + no login + paid-per-call means anyone can run
   up the LLM bill. Per-IP rate limiting, a global daily budget cap, and an input
   length limit handle this without accounts.
3. **Privacy hygiene on the log.** Free-text questions can carry sensitive intent
   (or accidental PII), are stored in plaintext, and are shown on the Usage tab.
   Gate the tab, consider anonymizing/retaining, and disclose that queries are sent
   to third-party model providers.

## The seam for accounts, if you ever want them

The FastAPI layer is exactly where identity bolts on: auth middleware puts a `user`
on each request; Ask history moves from browser `localStorage` to a per-user table;
quotas become per-user; routes gate by role. **The Python core — retrieval,
generation, evals — never learns that users exist.** That decoupling is the payoff
of having an API boundary at all.

## Takeaways

1. Split "multi-user" into **isolation / access / privacy / cost** — they are
   separate problems with separate answers.
2. A **shared, public corpus removes the hardest part** (data isolation) entirely.
3. For a public, no-auth app the real work is **access + abuse + privacy**, not
   identity — and identity, if ever needed, is a clean addition at the API seam.
