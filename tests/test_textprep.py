"""Unit tests for boilerplate detection: deterministic, no API/DB."""

from __future__ import annotations

from payments_rag.indexing.textprep import clean_page, find_repeated_lines

# Simulate a 6-page doc: same header (with varying page number) on every page,
# plus body text that varies in WORDS per page (real prose differs in words, not
# just digits; a line differing only by number would normalise to the same
# string and be wrongly flagged; that's an accepted limitation of digit-masking).
_BODIES = [
    "Alpha discusses instant settlement timing.",
    "Beta covers payment return handling.",
    "Gamma defines the BIC field precisely.",
    "Delta explains the charging principle.",
    "Epsilon lists the reason codes.",
    "Zeta describes the originating bank.",
]
PAGES = [
    f"www.epc-cep.eu {n}\nSEPA Rulebook 2025 Version 1.0\n{body}"
    for n, body in enumerate(_BODIES, start=1)
]


def test_detects_header_despite_varying_page_number() -> None:
    repeated = find_repeated_lines(PAGES)
    # digit-masked, the URL+page line and the title line recur on every page
    assert "www.epc-cep.eu #" in repeated
    assert "SEPA Rulebook # Version #.#" in repeated


def test_body_lines_are_not_flagged() -> None:
    repeated = find_repeated_lines(PAGES)
    assert "Beta covers payment return handling." not in repeated


def test_too_few_pages_returns_empty() -> None:
    # below min_pages we can't distinguish structure from content
    assert find_repeated_lines(PAGES[:2]) == set()


def test_clean_page_strips_boilerplate_and_keeps_body() -> None:
    repeated = find_repeated_lines(PAGES)
    cleaned = clean_page(PAGES[2], repeated)  # page 3 body is "Gamma ..."
    assert "www.epc-cep.eu" not in cleaned
    assert "SEPA Rulebook" not in cleaned
    assert "Gamma defines the BIC field precisely." in cleaned


def test_clean_page_fixes_bullet_artifact() -> None:
    cleaned = clean_page("� has received the transaction.", repeated=set())
    assert "�" not in cleaned
    assert "has received the transaction." in cleaned
