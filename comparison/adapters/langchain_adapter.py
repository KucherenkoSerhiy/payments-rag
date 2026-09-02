"""Comparator: the RAG pipeline built with LangChain components wired by a 2-node
LangGraph graph. Runs isolated, same models/corpus/top-k as the rest of the
comparison - see docs/adr/0019."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import TypedDict

import tiktoken
from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.graph import END, START, StateGraph
from pypdf import PdfReader

from comparison.logging_setup import get_logger
from comparison.schema import SystemAnswer

log = get_logger("comparison.langchain")

MODEL = "gpt-4o"
EMBED_MODEL = "text-embedding-3-small"
TOP_K = 5

INPUT_COST_PER_MTOK = 2.5    # gpt-4o list price, USD per 1M input tokens
OUTPUT_COST_PER_MTOK = 10.0  # gpt-4o list price, USD per 1M output tokens
EMBED_COST_PER_MTOK = 0.02   # text-embedding-3-small list price

# Standardized across the three framework comparators so chunk size isn't a hidden
# confound: ~1050 chars ~= Haystack's 200-word anchor (units never convert exactly).
CHUNK_SIZE_CHARS = 1050
CHUNK_OVERLAP_CHARS = 100

# LangChain's Embeddings interface doesn't surface token usage; count with tiktoken.
_ENCODER = tiktoken.encoding_for_model(EMBED_MODEL)

PROMPT_TEMPLATE = (
    "Answer the question using ONLY the sources below. If they do not contain the "
    "answer, say so.\n\n{context}\n\nQuestion: {question}"
)


class GraphState(TypedDict):
    question: str
    contexts: list[str]
    answer: str
    prompt_tokens: int
    completion_tokens: int


class LangChainIndexer:
    """Indexing block: corpus PDFs -> chunks -> InMemoryVectorStore.

    pypdf directly, not langchain_community's PyPDFLoader: that package is being
    sunset, and pypdf-direct is the extraction path this comparison already
    validated (docs/incidents/2026-08-29).
    """

    def build_store(self, pdf_paths: list[Path]) -> InMemoryVectorStore:
        documents = self.extract_text(pdf_paths)
        chunks = self.chunk(documents)
        index_tokens = sum(len(_ENCODER.encode(c.page_content)) for c in chunks)
        log.info(
            "indexed %d chunks from %d PDFs, $%.5f embedding cost",
            len(chunks), len(pdf_paths), index_tokens * EMBED_COST_PER_MTOK / 1_000_000,
        )
        return self.embed_and_store(chunks)

    def extract_text(self, pdf_paths: list[Path]) -> list[Document]:
        documents = []
        for path in pdf_paths:
            text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
            documents.append(Document(page_content=text, metadata={"file_name": path.name}))
        return documents

    def chunk(self, documents: list[Document]) -> list[Document]:
        return RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE_CHARS, chunk_overlap=CHUNK_OVERLAP_CHARS
        ).split_documents(documents)

    def embed_and_store(self, chunks: list[Document]) -> InMemoryVectorStore:
        """One framework call: add_documents embeds and stores in the same step."""
        store = InMemoryVectorStore(OpenAIEmbeddings(model=EMBED_MODEL))
        store.add_documents(chunks)
        return store


class LangChainRag:
    """Per-question orchestration: a compiled 2-node LangGraph whose nodes ARE the
    Retrieval and Generation blocks, plus normalization into SystemAnswer."""

    def __init__(self, store: InMemoryVectorStore) -> None:
        self._graph = self._build_graph(store)

    @staticmethod
    def _build_graph(store: InMemoryVectorStore):
        retriever = store.as_retriever(search_kwargs={"k": TOP_K})
        llm = ChatOpenAI(model=MODEL)

        def retrieve_node(state: GraphState) -> dict:
            docs = retriever.invoke(state["question"])
            return {"contexts": [d.page_content for d in docs]}

        def generate_node(state: GraphState) -> dict:
            prompt = PROMPT_TEMPLATE.format(
                context="\n\n".join(state["contexts"]), question=state["question"]
            )
            reply = llm.invoke(prompt)
            usage = reply.usage_metadata or {}
            return {
                "answer": reply.content,
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
            }

        builder = StateGraph(GraphState)
        builder.add_node("retrieve", retrieve_node)
        builder.add_node("generate", generate_node)
        builder.add_edge(START, "retrieve")
        builder.add_edge("retrieve", "generate")
        builder.add_edge("generate", END)
        return builder.compile()

    def answer(self, question_id: str, question: str, ground_truth: str) -> SystemAnswer:
        t0 = perf_counter()
        result = self._graph.invoke(
            {"question": question, "contexts": [], "answer": "", "prompt_tokens": 0, "completion_tokens": 0}
        )
        latency_s = perf_counter() - t0
        return self._to_system_answer(question_id, question, ground_truth, result, latency_s)

    def _to_system_answer(
        self, question_id: str, question: str, ground_truth: str, result: dict, latency_s: float
    ) -> SystemAnswer:
        prompt_tokens = result["prompt_tokens"]
        completion_tokens = result["completion_tokens"]
        cost_usd = (
            prompt_tokens * INPUT_COST_PER_MTOK + completion_tokens * OUTPUT_COST_PER_MTOK
        ) / 1_000_000 + len(_ENCODER.encode(question)) * EMBED_COST_PER_MTOK / 1_000_000

        return SystemAnswer(
            system="langchain",
            question_id=question_id,
            question=question,
            answer=result["answer"] or "",
            contexts=result["contexts"],
            citations=[],
            ground_truth=ground_truth,
            latency_s=latency_s,
            cost_usd=cost_usd,
            fidelity_note=(
                "no citation-extraction component used; plain context-injection via a "
                "2-node LangGraph graph (retrieve -> generate), not a grounded-citation pipeline"
            ),
            raw={"model": MODEL, "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        )


def build(pdf_paths: list[Path]) -> LangChainRag:
    """One-time setup (the Indexing block), then hand back the query-ready system."""
    return LangChainRag(LangChainIndexer().build_store(pdf_paths))
