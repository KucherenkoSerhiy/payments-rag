"""Document-level text cleanup, run before chunking.

PDFs stamp a header/footer on nearly every page. Here that's the EPC URL + page
number, the rulebook title, and the "Date issued" line. It's identical across
pages, so it carries no meaning, but it lands in every chunk and drags every
embedding toward the same noise, which flattens the similarity signal.

We remove it generically rather than hardcoding EPC strings: a line that recurs
on a large fraction of a document's pages is structural, not content. Page
numbers vary, so digits are masked before comparing ("page 35" == "page 36").

This is a frequency count over normalised strings: no ML, just DSA.
"""

from __future__ import annotations

import re
from collections import Counter

_DIGITS = re.compile(r"\d+")
_REPLACEMENT_CHAR = "�"  # the "" artifact from PDF bullet glyphs


def _normalise(line: str) -> str:
    """Collapse whitespace and mask digit runs so page numbers don't make every
    header line look unique."""
    return _DIGITS.sub("#", " ".join(line.split()))


def find_repeated_lines(
    pages: list[str], *, min_fraction: float = 0.5, min_pages: int = 4
) -> set[str]:
    """Return the set of *normalised* lines that appear on >= min_fraction of the
    document's pages. These are treated as header/footer boilerplate.

    Counts each line at most once per page (a line repeated within one page still
    counts as one), so the fraction is genuinely "on how many pages".
    """
    if len(pages) < min_pages:
        return set()  # too few pages to tell structure from content
    counts: Counter[str] = Counter()
    for page in pages:
        on_this_page = {_normalise(ln) for ln in page.splitlines() if ln.strip()}
        counts.update(on_this_page)
    cutoff = min_fraction * len(pages)
    return {line for line, freq in counts.items() if freq >= cutoff}


def clean_page(text: str, repeated: set[str]) -> str:
    """Drop boilerplate lines, fix the bullet artifact, and flatten to prose."""
    kept = [ln for ln in text.splitlines() if _normalise(ln) not in repeated]
    joined = " ".join(kept).replace(_REPLACEMENT_CHAR, " ")
    return " ".join(joined.split())  # collapse the whitespace left behind
