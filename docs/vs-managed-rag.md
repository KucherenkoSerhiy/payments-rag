# Versus managed RAG: what to integrate, and what stays out

`docs/prior-art.md` covers the retrieval-algorithm axis: which hand-rolled pieces
(fusion, reranking, IR metrics) have a mature library equivalent, and when to
reach for one. This doc covers a different axis: whole products and services
that could sit next to or inside this system, and the criterion for accepting
one.

## The criterion isn't accuracy

A benchmark of payments-rag against Gemini 3 with a million-token context on ten
questions is not a fight worth having, and it is not the point of owning this
stack. The actual reason to hand-roll a RAG instead of pointing a corpus at a
consumer tool is **integration**: the ability to run this inside a system where
the corpus, the queries, or both cannot leave the building. A payments engineer's
internal runbooks, incident postmortems, or system architecture notes are exactly
the kind of corpus where "upload it to a third party's hosted index" is not a
line-item decision, it is a security review. That is the lens every candidate
below is judged through, not answer quality.

## Two kinds of exposure, not one

"It's an API call" is not precise enough to reason about. Two categories matter:

- **Transient.** Text goes into a request, a vendor's model processes it, a
  response comes back. Nothing about your corpus persists on their
  infrastructure as a queryable asset afterward (subject to their stated data
  retention policy).
- **Persistent.** Your corpus, or a lossy-but-often-invertible representation of
  it (embeddings), gets stored on a third party's infrastructure as a
  standing index that continues to exist, and continues to be a breach target,
  after the request that created it is long done.

Persistent hosted exposure is categorically worse for the scenario above: a
breach at the vendor now includes your data, indefinitely, not just whatever
happened to be in flight during one call.

**What this system already accepts, stated plainly.** Two transient
relationships already exist and this doc does not re-litigate them: OpenAI sees
every chunk's raw text once, at embedding time. Anthropic sees every retrieved
chunk's raw text on every query, inside the generation prompt. Both are
per-call, neither is a new decision. The question below is only about *new*
categories of exposure.

## Libraries first: in-process, no new party sees anything

**RAGAS.** The genuinely strong candidate, and it clears the bar cleanly: it is
a Python library, installed and run in-process, and it scores answers by
calling whichever LLM you already point it at. That means it introduces zero
new recipients of corpus data, it reuses the existing GPT-4/Claude judge
relationship this project already has, and it slots directly onto the existing
golden set without changing what the judge is allowed to see. Its only default
outbound call is an anonymous usage-telemetry ping (package name, not corpus
data), and it has a documented kill switch: `RAGAS_DO_NOT_TRACK=true`.

It also gives four standard, recognized metrics (faithfulness, answer
relevancy, context precision, context recall) alongside the hand-built judge,
which is a real gap today: the current judge grades *correctness*, not whether
the answer was actually grounded in what was retrieved. Faithfulness is exactly
that missing check.

Separately, `ragas.io` is a hosted dashboard/tracing product built by the same
team. It is not required to use the metrics library, it is a different product
with a different trust model, and it is out of scope here unless raised on its
own.

The retrieval-side library candidates (`ranx`, the BGE cross-encoder reranker,
`ParadeDB`) are already covered in `prior-art.md` and are not repeated here.
They are all self-hosted or in-process by the same test and were already judged
on merit, independent of this security framing.

## APIs: held to a higher bar

An API is not automatically out, but it has to clear a specific question this
library-first default doesn't need to answer: **does using it change who has a
standing copy of the corpus, or does it just change what an already-trusted
call returns?**

**Anthropic's Citations API clears it, conditionally.** It is not a competing
RAG system, it is a citation-grounding primitive: you still do retrieval
yourself and still pass in the documents, Claude extracts and annotates
verifiable citations from what you gave it. Every payments-rag query already
sends the retrieved chunks to Claude in the generation prompt today. Adopting
Citations changes the shape of that same already-existing call; it does not add
a new party to the trust boundary, and it does not create a persistent
third-party index. That is the justification for treating it differently from
everything else in this section, not just "it's from a vendor we already use."
It would replace the hand-rolled `{answer, citations: [chunk_id]}` JSON parsing
in `payments_rag/answering/orchestrator.py` and `adapters/llm.py`, so it is still a real
code change and needs its own go-ahead before anything is touched.

**OpenAI's `file_search` (Responses API) does not clear it.** Uploading the
corpus creates a persistent, OpenAI-managed vector store that exists as a
queryable index independent of any single call. That is exactly the new
persistent exposure this doc is testing against. Cheap (~$0.03 for the whole golden set)
and technically strong, but it fails the actual criterion, not a cost or
quality one.

**Vectara does not clear it, and is moot anyway.** Same persistent-index
problem as `file_search`, at enterprise pricing ($100k+/year, no accessible
free tier found) that rules it out for a solo project regardless.

## The vector store nuance: self-hosted vs. cloud is the whole decision

`prior-art.md` names Qdrant/Weaviate as the off-ramp if hybrid search ever
needs to earn its keep on a bigger corpus. That recommendation stands, but it
needs one more sentence this security framing surfaces: **self-hosted Qdrant**
(a container you run, same trust model as the Postgres container this project
already runs) is fine by this test. **Qdrant Cloud** is not: a free tier
doesn't change that it is a third party holding a persistent, standing copy of
the corpus's embeddings. If retrieval quality ever justifies moving to Qdrant,
the compliant version is self-hosted, not the managed one.

## NotebookLM

For a one-off, non-integrated question over a personal PDF pile, NotebookLM is
the right tool and this project has no reason to compete with it there.

## What this doc recommends, pending separate go-ahead on each

1. **RAGAS as an additive eval layer.** Lowest risk, no architecture change,
   fills the faithfulness gap the current judge doesn't check. The natural next
   step if this doc is approved.
2. **Citations API as a possible replacement for the hand-rolled citation
   parsing.** Real code change, needs its own review before anything in
   `payments_rag/` is touched.
3. **Everything else in this doc (`file_search`, Vectara, Qdrant Cloud) is a
   documented no, not an open question.** They are recorded here so the
   reasoning is visible, not because they are pending a decision.

Nothing above has been installed, called, or implemented. This is the analysis;
the two numbered items above still need an explicit yes before any code
changes.
