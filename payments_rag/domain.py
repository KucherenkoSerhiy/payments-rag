"""Shared value objects. Pure data; imports nothing from the other layers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetrievedChunk:
    id: int
    source: str
    page: int | None
    text: str
    distance: float  # cosine distance, 0 = identical direction


@dataclass
class Citation:
    chunk_id: int
    source: str
    page: int | None
    text: str  # the passage itself, so the UI can show the evidence, not just a page ref


@dataclass
class AnswerResult:
    answer: str
    citations: list[Citation]
    retrieved_chunks: list[RetrievedChunk] = field(default_factory=list)  # the full top-k, not just cited ones
    retrieval_s: float = 0.0   # seconds spent embedding + searching
    generation_s: float = 0.0  # seconds spent in the LLM call
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0      # estimated LLM cost for this answer


@dataclass
class IndexStats:
    source: str
    pages: int
    pages_with_text: int
    chunks: int
