"""Comparator: the RAG pipeline built with Haystack (deepset). Runs isolated,
same models/corpus/top-k as the rest of the comparison - see docs/adr/0019."""

from __future__ import annotations

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


class HaystackIndexer:
    """Indexing block: corpus PDFs -> chunks -> embeddings -> in-memory store."""

    def build_store(self, pdf_paths: list[Path]) -> InMemoryDocumentStore:
        documents = self.extract_text(pdf_paths)
        chunks = self.chunk(documents)
        embedded, embed_cost = self.embed_corpus(chunks)
        log.info(
            "indexed %d chunks from %d PDFs, $%.5f embedding cost",
            len(embedded), len(pdf_paths), embed_cost,
        )
        return self.store(embedded)

    def extract_text(self, pdf_paths: list[Path]) -> list[Document]:
        return PyPDFToDocument().run(sources=pdf_paths)["documents"]

    def chunk(self, documents: list[Document]) -> list[Document]:
        # word-based, NOT sentence-based: sentence mode silently dropped oversized chunks
        # on this corpus (docs/incidents/2026-08-29). The 200-word size is also the anchor
        # the other two comparators' CHUNK_SIZE_* constants are converted to match.
        return DocumentSplitter(split_by="word", split_length=200, split_overlap=20).run(
            documents=documents
        )["documents"]

    def embed_corpus(self, chunks: list[Document]) -> tuple[list[Document], float]:
        result = OpenAIDocumentEmbedder(model=EMBED_MODEL).run(documents=chunks)
        embedded: list[Document] = result["documents"]
        failed = len(chunks) - len(embedded)
        if failed:
            log.warning("%d of %d chunks failed to embed and were dropped from the index", failed, len(chunks))
        tokens = result.get("meta", {}).get("usage", {}).get("prompt_tokens", 0)
        return embedded, tokens * EMBED_COST_PER_MTOK / 1_000_000

    def store(self, embedded: list[Document]) -> InMemoryDocumentStore:
        document_store = InMemoryDocumentStore()
        document_store.write_documents(embedded)
        return document_store


class HaystackRetriever:
    """Retrieval block: question -> top-k context passages (+ query embed tokens)."""

    def __init__(self, store: InMemoryDocumentStore) -> None:
        self._embedder = OpenAITextEmbedder(model=EMBED_MODEL)
        self._retriever = InMemoryEmbeddingRetriever(document_store=store, top_k=TOP_K)

    def retrieve(self, question: str) -> tuple[list[str], int]:
        vector, embed_tokens = self.embed_question(question)
        return self.search(vector), embed_tokens

    def embed_question(self, question: str) -> tuple[list[float], int]:
        result = self._embedder.run(text=question)
        return result["embedding"], result.get("meta", {}).get("usage", {}).get("prompt_tokens", 0)

    def search(self, vector: list[float]) -> list[str]:
        retrieved: list[Document] = self._retriever.run(query_embedding=vector)["documents"]
        return [d.content for d in retrieved if d.content]


class HaystackGenerator:
    """Generation block: question + contexts -> answer text (+ LLM token usage)."""

    def __init__(self) -> None:
        self._generator = OpenAIChatGenerator(model=MODEL)

    def generate(self, question: str, contexts: list[str]) -> tuple[str, int, int]:
        prompt = self.build_prompt(question, contexts)
        reply = self._generator.run(messages=[ChatMessage.from_user(prompt)])["replies"][0]
        usage = reply.meta.get("usage", {}) or {}
        return reply.text or "", usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)

    def build_prompt(self, question: str, contexts: list[str]) -> str:
        return PROMPT_TEMPLATE.format(context="\n\n".join(contexts), question=question)


class HaystackRag:
    """Per-question orchestration: Retrieval -> Generation -> shared SystemAnswer."""

    def __init__(self, retriever: HaystackRetriever, generator: HaystackGenerator) -> None:
        self._retriever = retriever
        self._generator = generator

    def answer(self, question_id: str, question: str, ground_truth: str) -> SystemAnswer:
        t0 = perf_counter()
        contexts, query_embed_tokens = self._retriever.retrieve(question)
        text, prompt_tokens, completion_tokens = self._generator.generate(question, contexts)
        latency_s = perf_counter() - t0

        cost_usd = (
            prompt_tokens * INPUT_COST_PER_MTOK + completion_tokens * OUTPUT_COST_PER_MTOK
        ) / 1_000_000 + query_embed_tokens * EMBED_COST_PER_MTOK / 1_000_000

        return SystemAnswer(
            system="haystack",
            question_id=question_id,
            question=question,
            answer=text,
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


def build(pdf_paths: list[Path]) -> HaystackRag:
    """One-time setup (the Indexing block), then hand back the query-ready system."""
    store = HaystackIndexer().build_store(pdf_paths)
    return HaystackRag(HaystackRetriever(store), HaystackGenerator())
