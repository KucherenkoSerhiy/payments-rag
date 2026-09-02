"""Tests for contextual indexing: blurbs shape the embedding, never the stored text."""

from __future__ import annotations

from payments_rag.indexing import indexer as indexer_module
from payments_rag.indexing.indexer import CorpusIndexer


class _FakeConn:
    def commit(self) -> None:
        pass


def _run_indexer(monkeypatch, tmp_path, *, contextual: bool, blurbs_fail: bool = False):
    """Index one tiny fake PDF; capture what gets embedded vs what gets stored."""
    embedded: list[str] = []
    stored: list[str] = []

    monkeypatch.setattr(indexer_module.pdf, "read_pages", lambda path: ["Settlement takes 5 seconds."])
    monkeypatch.setattr(
        indexer_module,
        "embed",
        lambda texts: (embedded.extend(texts), [[0.0] * 3 for _ in texts])[1],
    )
    monkeypatch.setattr(indexer_module.db, "delete_source", lambda conn, source: 0)
    monkeypatch.setattr(
        indexer_module.db,
        "insert_chunk",
        lambda conn, *, source, page, chunk_index, text, embedding: stored.append(text),
    )

    from payments_rag.adapters import contextualizer

    monkeypatch.setattr(contextualizer, "summarize_document", lambda source, text: "SCT Inst rulebook.")
    if blurbs_fail:
        monkeypatch.setattr(
            contextualizer, "contextualize_chunks",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("api down")),
        )
    else:
        monkeypatch.setattr(
            contextualizer, "contextualize_chunks",
            lambda source, summary, page_no, page_text, chunks: [f"CTX[{c[:10]}]" for c in chunks],
        )

    pdf_file = tmp_path / "doc.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 fake")
    CorpusIndexer(_FakeConn(), contextual=contextual).index_pdf(pdf_file)
    return embedded, stored


def test_plain_indexing_embeds_exactly_the_stored_text(monkeypatch, tmp_path) -> None:
    embedded, stored = _run_indexer(monkeypatch, tmp_path, contextual=False)
    assert embedded == stored == ["Settlement takes 5 seconds."]


def test_contextual_embeds_blurb_but_stores_verbatim_chunk(monkeypatch, tmp_path) -> None:
    embedded, stored = _run_indexer(monkeypatch, tmp_path, contextual=True)
    assert stored == ["Settlement takes 5 seconds."]  # cited evidence stays verbatim (ADR-0006)
    assert embedded[0].startswith("CTX[") and embedded[0].endswith("Settlement takes 5 seconds.")


def test_contextualization_failure_falls_back_to_bare_chunks(monkeypatch, tmp_path) -> None:
    embedded, stored = _run_indexer(monkeypatch, tmp_path, contextual=True, blurbs_fail=True)
    assert embedded == stored == ["Settlement takes 5 seconds."]  # degraded, not aborted
