"""Chunk contextualizer: situate each chunk in its document before embedding.

Contextual Retrieval (ADR-0023): a bare "5 seconds" chunk embeds poorly because
nothing says what the 5 seconds is about; a one-line blurb ("SCT Inst rulebook,
target maximum execution time...") prepended at embed time makes it findable.
Blurbs are generated per page (all of a page's chunks in one call) against a
one-time document summary, and are never stored or shown - cited evidence stays
verbatim spec text (ADR-0006).
"""

from __future__ import annotations

import json

from anthropic import Anthropic

from payments_rag import config

_client: Anthropic | None = None

# Keep the one-time summary call bounded even for a very large document.
_MAX_DOC_CHARS = 400_000


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(
            api_key=config.require_anthropic_key(),
            timeout=config.API_TIMEOUT,
            max_retries=config.API_MAX_RETRIES,
        )
    assert _client is not None
    return _client


def summarize_document(source: str, doc_text: str) -> str:
    """One ~150-word orientation summary per document, reused for every page."""
    resp = _get_client().messages.create(
        model=config.LLM_MODEL,
        max_tokens=400,
        temperature=0.0,
        messages=[{
            "role": "user",
            "content": (
                "Summarize this payments-scheme document in at most 150 words: what "
                "scheme it governs, and its main topic areas. The summary will be "
                "used to give retrieval context to individual passages.\n\n"
                f"DOCUMENT ({source}):\n{doc_text[:_MAX_DOC_CHARS]}"
            ),
        }],
    )
    return resp.content[0].text.strip()


def contextualize_chunks(
    source: str, doc_summary: str, page_no: int, page_text: str, chunks: list[str]
) -> list[str]:
    """One 1-2 sentence blurb per chunk, situating it in document and page.

    Raises on any API/parse failure; the indexer falls back to un-contextualized
    embedding for that page rather than aborting the run.
    """
    numbered = "\n\n".join(f"CHUNK {i}:\n{c}" for i, c in enumerate(chunks))
    resp = _get_client().messages.create(
        model=config.LLM_MODEL,
        max_tokens=250 + 120 * len(chunks),
        temperature=0.0,
        messages=[{
            "role": "user",
            "content": (
                "For each chunk below, write a succinct 1-2 sentence context that "
                "situates it within the document, naming the scheme and the specific "
                "topic/rule it belongs to, to improve search retrieval of the chunk. "
                f"Answer with a JSON array of exactly {len(chunks)} strings, nothing else.\n\n"
                f"DOCUMENT: {source}\nDOCUMENT SUMMARY: {doc_summary}\n"
                f"PAGE {page_no} TEXT:\n{page_text}\n\n{numbered}"
            ),
        }],
    )
    text = resp.content[0].text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    blurbs = json.loads(text)
    if not isinstance(blurbs, list) or len(blurbs) != len(chunks):
        raise ValueError(f"expected {len(chunks)} blurbs, got {blurbs!r:.120}")
    return [str(b).strip() for b in blurbs]
