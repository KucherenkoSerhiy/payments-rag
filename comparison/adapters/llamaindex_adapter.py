"""Comparator: the RAG pipeline built with LlamaIndex. Runs isolated, same
models/corpus/top-k as the rest of the comparison - see docs/adr/0019."""

from __future__ import annotations

import re
from pathlib import Path
from time import perf_counter

from llama_index.core import Document, Settings, VectorStoreIndex
from llama_index.core.callbacks import CallbackManager, TokenCountingHandler
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI as OpenAILLM
from pypdf import PdfReader

from comparison.logging_setup import get_logger
from comparison.schema import SystemAnswer

log = get_logger("comparison.llamaindex")

MODEL = "gpt-4o"
EMBED_MODEL = "text-embedding-3-small"
TOP_K = 5

# Standardized across the three framework comparators so chunk size isn't a hidden
# confound: ~250 tokens ~= Haystack's 200-word anchor (units never convert exactly).
CHUNK_SIZE_TOKENS = 250
CHUNK_OVERLAP_TOKENS = 25

INPUT_COST_PER_MTOK = 2.5    # gpt-4o list price, USD per 1M input tokens
OUTPUT_COST_PER_MTOK = 10.0  # gpt-4o list price, USD per 1M output tokens
EMBED_COST_PER_MTOK = 0.02   # text-embedding-3-small list price

# LlamaIndex's default PDF reader silently leaked XMP metadata into extracted text and
# garbled pages on this corpus (docs/incidents/2026-08-29): load with pypdf directly
# instead, and strip any XMP packet as defense in depth.
_XMP_PACKET = re.compile(r"<\?xpacket begin.*?<\?xpacket end=\"w\"\?>", re.DOTALL)


class LlamaIndexIndexer:
    """Indexing block: corpus PDFs (pypdf-direct) -> VectorStoreIndex."""

    def __init__(self, token_counter: TokenCountingHandler) -> None:
        self._token_counter = token_counter

    def build_index(self, pdf_paths: list[Path]) -> VectorStoreIndex:
        documents = self.extract_text(pdf_paths)
        index = self.chunk_embed_store(documents)
        log.info(
            "indexed %d source docs, $%.5f embedding cost",
            len(documents),
            self._token_counter.total_embedding_token_count * EMBED_COST_PER_MTOK / 1_000_000,
        )
        self._token_counter.reset_counts()
        return index

    def extract_text(self, pdf_paths: list[Path]) -> list[Document]:
        documents = []
        for path in pdf_paths:
            text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
            cleaned, n = _XMP_PACKET.subn("", text)
            if n:
                log.warning("%s: stripped %d embedded XMP metadata packet(s) from extracted text", path.name, n)
            documents.append(Document(text=cleaned, metadata={"file_name": path.name}))
        return documents

    def chunk_embed_store(self, documents: list[Document]) -> VectorStoreIndex:
        """One framework call does all three steps; there is no seam to split them at."""
        splitter = SentenceSplitter(chunk_size=CHUNK_SIZE_TOKENS, chunk_overlap=CHUNK_OVERLAP_TOKENS)
        return VectorStoreIndex.from_documents(documents, transformations=[splitter])


class LlamaIndexRag:
    """Retrieval + Generation - fused by the framework: one query() call does both,
    so unlike Haystack/LangChain there is no seam here to split along."""

    def __init__(self, index: VectorStoreIndex, token_counter: TokenCountingHandler) -> None:
        self._query_engine = index.as_query_engine(similarity_top_k=TOP_K)
        self._token_counter = token_counter

    def answer(self, question_id: str, question: str, ground_truth: str) -> SystemAnswer:
        self._token_counter.reset_counts()
        t0 = perf_counter()
        response = self.retrieve_and_generate(question)
        latency_s = perf_counter() - t0
        return self._to_system_answer(question_id, question, ground_truth, response, latency_s)

    def retrieve_and_generate(self, question: str):
        return self._query_engine.query(question)

    def _to_system_answer(
        self, question_id: str, question: str, ground_truth: str, response, latency_s: float
    ) -> SystemAnswer:
        contexts = [n.node.get_content() for n in response.source_nodes]
        citations = [
            f"{n.node.metadata.get('file_name', 'unknown')} (score {n.score:.3f})"
            for n in response.source_nodes
            if n.score is not None
        ]

        prompt_tokens = self._token_counter.prompt_llm_token_count
        completion_tokens = self._token_counter.completion_llm_token_count
        embed_tokens = self._token_counter.total_embedding_token_count
        cost_usd = (
            prompt_tokens * INPUT_COST_PER_MTOK + completion_tokens * OUTPUT_COST_PER_MTOK
        ) / 1_000_000 + embed_tokens * EMBED_COST_PER_MTOK / 1_000_000

        return SystemAnswer(
            system="llamaindex",
            question_id=question_id,
            question=question,
            answer=response.response or "",
            contexts=contexts,
            citations=citations,
            ground_truth=ground_truth,
            latency_s=latency_s,
            cost_usd=cost_usd,
            raw={"model": MODEL, "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        )


def build(pdf_paths: list[Path]) -> LlamaIndexRag:
    """One-time setup (the Indexing block), then hand back the query-ready system."""
    token_counter = TokenCountingHandler()
    Settings.llm = OpenAILLM(model=MODEL)
    Settings.embed_model = OpenAIEmbedding(model=EMBED_MODEL)
    Settings.callback_manager = CallbackManager([token_counter])

    index = LlamaIndexIndexer(token_counter).build_index(pdf_paths)
    return LlamaIndexRag(index, token_counter)
