"""One matrix pipeline: index a topic with an embedder, answer with a generator.

The answer prompt is identical for every generator - the prompt must never be
a hidden variable. It mirrors the production payments-rag contract (answer
only from the provided context, cite sources, admit when the context doesn't
contain the answer) in topic-neutral wording.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from comparison.logging_setup import get_logger
from comparison.matrix import providers
from comparison.matrix.config import CHAT_MODELS, EMBED_MODELS, TOP_K, Pipeline
from comparison.matrix.corpus import load_chunks
from comparison.matrix.store import VectorStore

log = get_logger("matrix.pipeline")

# Embedding batch size: conservative enough for every provider's request caps.
_EMBED_BATCH = 64

ANSWER_PROMPT = """\
Answer the question using ONLY the context passages below. If the context does
not contain the answer, say you cannot answer from the provided documents.
Be concise and factual. End with "Sources:" listing the file name(s) of the
passages you actually used.

{contexts}

QUESTION: {question}
"""


@dataclass(frozen=True)
class Answer:
    answer: str
    contexts: list[str]      # retrieved passage texts, rank order
    sources: list[str]       # file names of the retrieved passages, rank order
    latency_s: float         # embed-query + retrieve + generate, per question
    cost_usd: float          # query-time cost only (see IndexedTopic for indexing cost)


class IndexedTopic:
    """A topic indexed under one pipeline's embedder, ready to answer questions."""

    def __init__(self, pipeline: Pipeline, topic: str) -> None:
        self.pipeline = pipeline
        self.topic = topic
        self.embed_model = EMBED_MODELS[pipeline.embed]
        self.chat_model = CHAT_MODELS[pipeline.chat]
        self.store = VectorStore()
        self.index_cost_usd = 0.0

        chunks = load_chunks(topic)
        for start in range(0, len(chunks), _EMBED_BATCH):
            batch = chunks[start:start + _EMBED_BATCH]
            vectors, tokens = providers.embed(self.embed_model, [c.text for c in batch])
            self.store.add(batch, vectors)
            self.index_cost_usd += providers.embed_cost_usd(self.embed_model, tokens)
        log.info(
            "%s/%s: indexed %d chunks (~$%.4f)",
            pipeline.key, topic, len(self.store), self.index_cost_usd,
        )

    def answer(self, question: str) -> Answer:
        started = perf_counter()
        q_vectors, q_tokens = providers.embed(self.embed_model, [question])
        hits = self.store.search(q_vectors[0], TOP_K)

        contexts = [chunk.text for chunk, _ in hits]
        sources = [chunk.source for chunk, _ in hits]
        rendered = "\n\n".join(
            f"[{i + 1}] (from {chunk.source})\n{chunk.text}"
            for i, (chunk, _) in enumerate(hits)
        )
        result = providers.chat(
            self.chat_model,
            ANSWER_PROMPT.format(contexts=rendered, question=question),
        )
        cost = providers.embed_cost_usd(self.embed_model, q_tokens) + providers.chat_cost_usd(
            self.chat_model, result.input_tokens, result.output_tokens
        )
        return Answer(
            answer=result.text.strip(),
            contexts=contexts,
            sources=sources,
            latency_s=round(perf_counter() - started, 2),
            cost_usd=round(cost, 6),
        )
