"""Comparator: OpenAI's Responses API `file_search` tool - "RAG in a box".
Comparison-only, never an integration target: the vector store is a persistent
OpenAI-hosted copy of the corpus (docs/vs-managed-rag.md)."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

from openai import OpenAI

from comparison.logging_setup import get_logger
from comparison.schema import SystemAnswer
from payments_rag import config

log = get_logger("comparison.openai_filesearch")

MODEL = "gpt-4o"
INPUT_COST_PER_MTOK = 2.5    # gpt-4o list price, USD per 1M input tokens
OUTPUT_COST_PER_MTOK = 10.0  # gpt-4o list price, USD per 1M output tokens
FILE_SEARCH_COST_PER_1K_CALLS = 2.50  # USD; first 1GB/day storage is free, this corpus is well under it


def _client() -> OpenAI:
    return OpenAI(api_key=config.require_openai_key())


class OpenAIFileSearchIndexer:
    """Indexing block - happens vendor-side: upload PDFs, OpenAI chunks/embeds/stores."""

    def upload_corpus(self, pdf_paths: list[Path], name: str = "payments-rag-comparison") -> str:
        client = _client()
        vs = client.vector_stores.create(name=name)
        log.info("created vector store %s (%s)", vs.id, name)
        for path in pdf_paths:
            with path.open("rb") as f:
                file_obj = client.files.create(file=f, purpose="assistants")
            client.vector_stores.files.create_and_poll(vector_store_id=vs.id, file_id=file_obj.id)
            log.info("indexed %s as file %s", path.name, file_obj.id)
        return vs.id


class OpenAIFileSearchRag:
    """Retrieval + Generation - fused vendor-side: one API call retrieves from the
    managed store and generates, so like LlamaIndex there is no seam to split."""

    def __init__(self, vector_store_id: str) -> None:
        self._vector_store_id = vector_store_id
        self._client = _client()

    def answer(self, question_id: str, question: str, ground_truth: str) -> SystemAnswer:
        t0 = perf_counter()
        resp = self.retrieve_and_generate(question)
        latency_s = perf_counter() - t0
        return self._to_system_answer(question_id, question, ground_truth, resp, latency_s)

    def retrieve_and_generate(self, question: str):
        return self._client.responses.create(
            model=MODEL,
            input=question,
            tools=[{"type": "file_search", "vector_store_ids": [self._vector_store_id]}],
            include=["file_search_call.results"],
        )

    def _to_system_answer(
        self, question_id: str, question: str, ground_truth: str, resp, latency_s: float
    ) -> SystemAnswer:
        answer_text, contexts, citations = self._parse_output(resp)
        usage = resp.usage
        cost_usd = (
            usage.input_tokens * INPUT_COST_PER_MTOK + usage.output_tokens * OUTPUT_COST_PER_MTOK
        ) / 1_000_000 + FILE_SEARCH_COST_PER_1K_CALLS / 1000

        return SystemAnswer(
            system="openai-file-search",
            question_id=question_id,
            question=question,
            answer=answer_text,
            contexts=contexts,
            citations=citations,
            ground_truth=ground_truth,
            latency_s=latency_s,
            cost_usd=cost_usd,
            raw={"response_id": resp.id, "model": MODEL, "vector_store_id": self._vector_store_id},
        )

    @staticmethod
    def _parse_output(resp) -> tuple[str, list[str], list[str]]:
        answer_text = ""
        contexts: list[str] = []
        citations: list[str] = []
        for item in resp.output:
            if item.type == "file_search_call" and item.results:
                contexts.extend(r.text for r in item.results)
            if item.type == "message":
                for block in item.content:
                    if block.type == "output_text":
                        answer_text += block.text
                        citations.extend(
                            f"{a.filename} (annotation idx {a.index})"
                            for a in block.annotations
                            if a.type == "file_citation"
                        )
        return answer_text, contexts, citations
