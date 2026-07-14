"""Tests for the orchestrator: the answer flow.

No DB and no API: `answer` is exercised with `retrieve`, `build_prompt`, and
`llm.complete_json` monkeypatched, so it tests only your wiring/mapping logic.
"""

from __future__ import annotations

from payments_rag.orchestrator import AnswerResult, Citation, answer, build_prompt
from payments_rag.retrieval.retriever import RetrievedChunk

CHUNKS = [
    RetrievedChunk(id=42, source="a.pdf", page=26, text="Settlement is 5 seconds.", distance=0.1),
    RetrievedChunk(id=7, source="b.pdf", page=3, text="Charges are shared.", distance=0.2),
]


def test_build_prompt_has_labeled_structure_and_tagged_chunks() -> None:
    prompt = build_prompt("How fast?", CHUNKS)
    # labeled sections
    assert "Question: How fast?" in prompt
    assert "Sources:" in prompt
    # each chunk tagged by id, with source + page, so the model can cite it
    assert "[chunk 42] (a.pdf p26)" in prompt
    assert "[chunk 7] (b.pdf p3)" in prompt
    # chunk text is present
    assert "Settlement is 5 seconds." in prompt


def test_answer_maps_cited_ids_and_ignores_invented_ones(monkeypatch) -> None:
    monkeypatch.setattr("payments_rag.orchestrator.retrieve", lambda conn, q, k=5: CHUNKS)
    monkeypatch.setattr("payments_rag.orchestrator.build_prompt", lambda q, chunks: "PROMPT")
    monkeypatch.setattr(
        "payments_rag.adapters.llm.complete_json",
        lambda prompt: (
            {"answer": "5 seconds.", "citations": [42, 999]},
            {"input_tokens": 120, "output_tokens": 30},
        ),
    )

    result = answer(None, "How fast?", k=2)

    assert isinstance(result, AnswerResult)
    assert result.answer == "5 seconds."
    # 42 -> a.pdf p26; 999 was never retrieved, so it's dropped
    assert result.citations == [
        Citation(chunk_id=42, source="a.pdf", page=26, text="Settlement is 5 seconds.")
    ]
