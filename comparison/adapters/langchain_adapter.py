"""Adapter: a RAG pipeline built with LangChain (retrieval primitives) and LangGraph
(control flow) instead of hand-rolling the orchestration ADR-0004 keeps out of
production. See docs/adr/0019 for why this comparator exists (alongside Haystack and
LlamaIndex) and why it only ever runs isolated (never a project dependency).

LangGraph is used the way it's actually used in practice: not as a replacement for RAG
components, but as the graph that wires LangChain's own retriever/vector store
together with the generation call. Two nodes - retrieve, generate - is the whole graph.

PDFs are loaded with pypdf directly, not langchain_community's PyPDFLoader:
langchain-community prints its own deprecation warning as of this writing ("being
sunset... no longer actively maintained"), and this comparison's own history
(docs/incidents/2026-08-29-comparison-corpus-and-extraction-bugs.md) already showed
pypdf-direct extraction is the reliable choice, having found and fixed a real
extraction defect in a different framework's default reader.

Same corpus, same golden set, same OpenAI models (gpt-4o + text-embedding-3-small) as
the rest of this comparison, and the same retrieval width (`TOP_K = 5`) as
payments-rag's own `orchestrator.answer(k=5)`.

Signatures below (langgraph 1.2.11, langchain-core 1.6.1, langchain-openai 1.6.0) were
confirmed by introspecting the installed packages, not assumed from docs - this
ecosystem crossed into 1.x majors since anything in training data would remember, and
the exact keyword (`search_kwargs`, not `k` directly) for retriever top-k was checked
by hand.
"""

from __future__ import annotations

from dataclasses import dataclass
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

# Standardized across all three framework comparators (Haystack, LlamaIndex, LangChain)
# so chunk size isn't a hidden confound in "hand-rolled vs. framework-orchestrated".
# Anchored on Haystack's 200-word chunks (its own documented default): ~200 words *
# ~5.3 chars/word (standard English average) ~= 1060, rounded to 1050; overlap kept at
# the same ~10% ratio. Word/token/character units never convert exactly - this is the
# closest common ground achievable across three different splitter designs, not a
# claim of identical chunking behavior.
CHUNK_SIZE_CHARS = 1050
CHUNK_OVERLAP_CHARS = 100

# LangChain's Embeddings interface doesn't surface token usage, unlike Haystack's and
# LlamaIndex's (both expose real usage via their own callback/meta mechanisms) - counted
# with tiktoken instead, OpenAI's own tokenizer, rather than approximating by word count.
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


@dataclass
class LangChainGraph:
    graph: object  # CompiledStateGraph[GraphState, ...]; left untyped to skip the generic


def _load_pdf_documents(pdf_paths: list[Path]) -> list[Document]:
    documents = []
    for path in pdf_paths:
        text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        documents.append(Document(page_content=text, metadata={"file_name": path.name}))
    return documents


def index_corpus(pdf_paths: list[Path]) -> LangChainGraph:
    """One-time setup: load, chunk, embed, and index the corpus PDFs; compile the graph."""
    documents = _load_pdf_documents(pdf_paths)
    chunks = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE_CHARS, chunk_overlap=CHUNK_OVERLAP_CHARS
    ).split_documents(documents)

    embeddings = OpenAIEmbeddings(model=EMBED_MODEL)
    store = InMemoryVectorStore(embeddings)
    store.add_documents(chunks)
    index_tokens = sum(len(_ENCODER.encode(c.page_content)) for c in chunks)
    log.info(
        "indexed %d chunks from %d PDFs, $%.5f embedding cost",
        len(chunks), len(pdf_paths), index_tokens * EMBED_COST_PER_MTOK / 1_000_000,
    )

    retriever = store.as_retriever(search_kwargs={"k": TOP_K})
    llm = ChatOpenAI(model=MODEL)

    def retrieve_node(state: GraphState) -> dict:
        docs = retriever.invoke(state["question"])
        return {"contexts": [d.page_content for d in docs]}

    def generate_node(state: GraphState) -> dict:
        prompt = PROMPT_TEMPLATE.format(context="\n\n".join(state["contexts"]), question=state["question"])
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

    return LangChainGraph(graph=builder.compile())


def answer(index: LangChainGraph, question_id: str, question: str, ground_truth: str) -> SystemAnswer:
    t0 = perf_counter()
    result = index.graph.invoke(
        {"question": question, "contexts": [], "answer": "", "prompt_tokens": 0, "completion_tokens": 0}
    )
    latency_s = perf_counter() - t0

    contexts = result["contexts"]
    prompt_tokens = result["prompt_tokens"]
    completion_tokens = result["completion_tokens"]
    query_embed_tokens = len(_ENCODER.encode(question))

    cost_usd = (
        prompt_tokens * INPUT_COST_PER_MTOK + completion_tokens * OUTPUT_COST_PER_MTOK
    ) / 1_000_000 + query_embed_tokens * EMBED_COST_PER_MTOK / 1_000_000

    log.info("%s: %.2fs, $%.5f, %d contexts", question_id, latency_s, cost_usd, len(contexts))
    return SystemAnswer(
        system="langchain",
        question_id=question_id,
        question=question,
        answer=result["answer"] or "",
        contexts=contexts,
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
