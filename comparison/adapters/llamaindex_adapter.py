"""Adapter: a RAG pipeline built with LlamaIndex instead of hand-rolling the
orchestration ADR-0004 keeps out of production. See docs/adr/0019 for why this
comparator exists (alongside Haystack) and why it only ever runs isolated (never a
project dependency).

Same corpus, same golden set, same OpenAI models (gpt-4o + text-embedding-3-small) as
the rest of this comparison, and the same retrieval width (`TOP_K = 5`) as
payments-rag's own `orchestrator.answer(k=5)` — this measures "hand-rolled vs.
framework-orchestrated", not "which vendor's models are better".

Signatures below (llama-index-core 0.14.24) were confirmed by introspecting the
installed package, not assumed from docs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from llama_index.core import Document, Settings, VectorStoreIndex
from llama_index.core.base.base_query_engine import BaseQueryEngine
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

# Standardized across all three framework comparators (Haystack, LlamaIndex, LangChain)
# so chunk size isn't a hidden confound in "hand-rolled vs. framework-orchestrated".
# Anchored on Haystack's 200-word chunks (its own documented default): ~200 words *
# ~1.33 tokens/word (standard English average) ~= 266, rounded to 250; overlap kept at
# the same ~10% ratio. Word/token/character units never convert exactly - this is the
# closest common ground achievable across three different splitter designs, not a
# claim of identical chunking behavior.
CHUNK_SIZE_TOKENS = 250
CHUNK_OVERLAP_TOKENS = 25

INPUT_COST_PER_MTOK = 2.5    # gpt-4o list price, USD per 1M input tokens
OUTPUT_COST_PER_MTOK = 10.0  # gpt-4o list price, USD per 1M output tokens
EMBED_COST_PER_MTOK = 0.02   # text-embedding-3-small list price

# LlamaIndex's default PDF reader (SimpleDirectoryReader's built-in loader, no extra
# `llama-index-readers-file` package installed) was found, by direct inspection, to
# produce two distinct defects on this corpus: (1) it dumps the raw Adobe XMP metadata
# packet embedded in both PDFs into extracted text verbatim, landing as a ~4.7KB junk
# chunk that won a top-5 retrieval slot for every golden-set question in an early run;
# (2) it produced outright garbled/corrupted binary-looking text for portions of at
# least one PDF (confirmed: every retrieved context for `sct-inst-max-execution-time`
# was unreadable noise, not real prose), causing the LLM to fall back on stale training
# knowledge because nothing usable was retrieved. Haystack's `PyPDFToDocument` (pypdf,
# PLAIN mode) extracts the same PDFs cleanly - confirmed side by side. Fix: bypass
# LlamaIndex's default reader entirely and load PDFs with pypdf directly, the same
# library Haystack already uses, then strip any XMP packet as defense in depth.
_XMP_PACKET = re.compile(r"<\?xpacket begin.*?<\?xpacket end=\"w\"\?>", re.DOTALL)


def _load_pdf_documents(pdf_paths: list[Path]) -> list[Document]:
    documents = []
    for path in pdf_paths:
        text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        cleaned, n = _XMP_PACKET.subn("", text)
        if n:
            log.warning("%s: stripped %d embedded XMP metadata packet(s) from extracted text", path.name, n)
        documents.append(Document(text=cleaned, metadata={"file_name": path.name}))
    return documents


@dataclass
class LlamaIndexQueryEngine:
    query_engine: BaseQueryEngine
    token_counter: TokenCountingHandler


def index_corpus(pdf_paths: list[Path]) -> LlamaIndexQueryEngine:
    """One-time setup: load, embed, and index the corpus PDFs in-memory."""
    token_counter = TokenCountingHandler()
    Settings.llm = OpenAILLM(model=MODEL)
    Settings.embed_model = OpenAIEmbedding(model=EMBED_MODEL)
    Settings.callback_manager = CallbackManager([token_counter])

    documents = _load_pdf_documents(pdf_paths)
    splitter = SentenceSplitter(chunk_size=CHUNK_SIZE_TOKENS, chunk_overlap=CHUNK_OVERLAP_TOKENS)
    index = VectorStoreIndex.from_documents(documents, transformations=[splitter])

    log.info(
        "indexed %d source docs, $%.5f embedding cost",
        len(documents),
        token_counter.total_embedding_token_count * EMBED_COST_PER_MTOK / 1_000_000,
    )
    token_counter.reset_counts()

    return LlamaIndexQueryEngine(
        query_engine=index.as_query_engine(similarity_top_k=TOP_K),
        token_counter=token_counter,
    )


def answer(index: LlamaIndexQueryEngine, question_id: str, question: str, ground_truth: str) -> SystemAnswer:
    index.token_counter.reset_counts()
    t0 = perf_counter()
    response = index.query_engine.query(question)
    latency_s = perf_counter() - t0

    contexts = [n.node.get_content() for n in response.source_nodes]
    citations = [
        f"{n.node.metadata.get('file_name', 'unknown')} (score {n.score:.3f})"
        for n in response.source_nodes
        if n.score is not None
    ]

    prompt_tokens = index.token_counter.prompt_llm_token_count
    completion_tokens = index.token_counter.completion_llm_token_count
    embed_tokens = index.token_counter.total_embedding_token_count
    cost_usd = (
        prompt_tokens * INPUT_COST_PER_MTOK + completion_tokens * OUTPUT_COST_PER_MTOK
    ) / 1_000_000 + embed_tokens * EMBED_COST_PER_MTOK / 1_000_000

    log.info("%s: %.2fs, $%.5f, %d contexts", question_id, latency_s, cost_usd, len(contexts))
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
