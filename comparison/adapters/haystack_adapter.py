"""Adapter: a RAG pipeline built with Haystack (deepset) instead of hand-rolling the
orchestration ADR-0004 keeps out of production. See docs/adr/0019 for why this
comparator exists and why it only ever runs isolated (never a project dependency).

Same corpus, same golden set, same OpenAI models (gpt-4o + text-embedding-3-small) as
the rest of this comparison — this measures "hand-rolled vs. framework-orchestrated",
not "which vendor's models are better". Retrieval width (`TOP_K = 5`) matches
payments-rag's own `orchestrator.answer(k=5)` for the same reason.

Component signatures below (Haystack 3.1.0) were confirmed by introspecting the
installed package, not assumed from docs — this framework moves fast enough that
stale API memory is a real risk.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from haystack import Document
from haystack.components.converters import PyPDFToDocument
from haystack.components.embedders import OpenAIDocumentEmbedder, OpenAITextEmbedder
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.components.preprocessors import DocumentSplitter
from haystack.components.retrievers.in_memory import InMemoryEmbeddingRetriever
from haystack.dataclasses import ChatMessage
from haystack.document_stores.in_memory import InMemoryDocumentStore

from comparison.logging_setup import get_logger
from comparison.schema import SystemAnswer

log = get_logger("comparison.haystack")

MODEL = "gpt-4o"
EMBED_MODEL = "text-embedding-3-small"
TOP_K = 5

INPUT_COST_PER_MTOK = 2.5    # gpt-4o list price, USD per 1M input tokens
OUTPUT_COST_PER_MTOK = 10.0  # gpt-4o list price, USD per 1M output tokens
EMBED_COST_PER_MTOK = 0.02   # text-embedding-3-small list price

PROMPT_TEMPLATE = (
    "Answer the question using ONLY the sources below. If they do not contain the "
    "answer, say so.\n\n{context}\n\nQuestion: {question}"
)


@dataclass
class HaystackIndex:
    text_embedder: OpenAITextEmbedder
    retriever: InMemoryEmbeddingRetriever
    generator: OpenAIChatGenerator


def index_corpus(pdf_paths: list[Path]) -> HaystackIndex:
    """One-time setup: convert, split, embed, and store the corpus PDFs in-memory."""
    docs = PyPDFToDocument().run(sources=pdf_paths)["documents"]
    # word-based splitting, not sentence-based: PyPDF's extracted text has no clean
    # sentence boundaries in tables/multi-column regulatory layout, which made nltk's
    # sentence tokenizer occasionally treat a whole malformed block as one "sentence" -
    # a chunk over the 8192-token embedding limit, silently dropped from the index.
    # split_length=200 is Haystack's own documented default; word-based splitting
    # caps chunk size directly, independent of punctuation quality. This 200-word
    # size is also the anchor the LlamaIndex and LangChain adapters' chunk sizes are
    # converted to match (see their own CHUNK_SIZE_* constants) - a hidden mismatch
    # here would otherwise confound "framework quality" with "chunk size" across the
    # three comparators.
    chunks = DocumentSplitter(split_by="word", split_length=200, split_overlap=20).run(
        documents=docs
    )["documents"]

    embed_result = OpenAIDocumentEmbedder(model=EMBED_MODEL).run(documents=chunks)
    embedded: list[Document] = embed_result["documents"]
    embed_tokens = embed_result.get("meta", {}).get("usage", {}).get("prompt_tokens", 0)
    failed = len(chunks) - len(embedded)
    if failed:
        log.warning("%d of %d chunks failed to embed and were dropped from the index", failed, len(chunks))

    document_store = InMemoryDocumentStore()
    document_store.write_documents(embedded)
    log.info(
        "indexed %d chunks from %d PDFs, $%.5f embedding cost",
        len(embedded), len(pdf_paths), embed_tokens * EMBED_COST_PER_MTOK / 1_000_000,
    )

    return HaystackIndex(
        text_embedder=OpenAITextEmbedder(model=EMBED_MODEL),
        retriever=InMemoryEmbeddingRetriever(document_store=document_store, top_k=TOP_K),
        generator=OpenAIChatGenerator(model=MODEL),
    )


def answer(index: HaystackIndex, question_id: str, question: str, ground_truth: str) -> SystemAnswer:
    t0 = perf_counter()

    embed_result = index.text_embedder.run(text=question)
    query_embed_tokens = embed_result.get("meta", {}).get("usage", {}).get("prompt_tokens", 0)

    retrieved: list[Document] = index.retriever.run(query_embedding=embed_result["embedding"])["documents"]
    contexts = [d.content for d in retrieved if d.content]

    prompt = PROMPT_TEMPLATE.format(context="\n\n".join(contexts), question=question)
    reply = index.generator.run(messages=[ChatMessage.from_user(prompt)])["replies"][0]
    latency_s = perf_counter() - t0

    usage = reply.meta.get("usage", {}) or {}
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    cost_usd = (
        prompt_tokens * INPUT_COST_PER_MTOK + completion_tokens * OUTPUT_COST_PER_MTOK
    ) / 1_000_000 + query_embed_tokens * EMBED_COST_PER_MTOK / 1_000_000

    log.info("%s: %.2fs, $%.5f, %d contexts", question_id, latency_s, cost_usd, len(contexts))
    return SystemAnswer(
        system="haystack",
        question_id=question_id,
        question=question,
        answer=reply.text or "",
        contexts=contexts,
        citations=[],
        ground_truth=ground_truth,
        latency_s=latency_s,
        cost_usd=cost_usd,
        fidelity_note=(
            "no citation-extraction component used; this is plain context-injection, "
            "not a grounded-citation pipeline like the other adapters"
        ),
        raw={"model": MODEL, "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    )
