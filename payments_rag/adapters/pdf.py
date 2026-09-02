"""PDF adapter: file on disk -> raw per-page text."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


def read_pages(path: str | Path) -> list[str]:
    """Extract text per page; a page with no extractable text becomes ''."""
    return [page.extract_text() or "" for page in PdfReader(str(path)).pages]
