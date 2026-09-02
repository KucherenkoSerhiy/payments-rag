"""One-shot converter: corpus/topics/*/raw HTML/PDF sources -> clean .txt files.

Stdlib + pypdf only (no new dependencies). Produces the plain-text corpus files
the model-matrix experiment (article 06) chunks and indexes. Originals are kept
in each topic's raw/ subfolder; the harness reads only *.txt / *.md at the
topic root.

Extraction is deliberately inspected by hand after running (see the
docs/incidents 2026-08-29 writeup: silent extraction junk cost days in the
article-05 comparison) - this script errs on the side of dropping boilerplate
rather than keeping everything.

Run once from the repo root:

    PYTHONIOENCODING=utf-8 python scripts/convert_topic_corpus.py
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from pypdf import PdfReader

TOPICS = Path("corpus/topics")

# Tags whose entire subtree is never content.
_SKIP_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "form", "svg", "button"}
_BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "dt", "dd", "blockquote", "ul", "ol", "table"}


class _TextExtractor(HTMLParser):
    """Collects block-level text, skipping script/style/nav subtrees."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._chunks: list[str] = []
        self._current: list[str] = []
        self._heading: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS and self._skip_depth == 0:
            self._flush()
            if tag in {"h1", "h2", "h3", "h4"}:
                self._heading = tag

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in _BLOCK_TAGS and self._skip_depth == 0:
            self._flush()
            self._heading = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data.strip():
            self._current.append(data)

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", " ".join(self._current)).strip()
        self._current = []
        if not text:
            return
        if self._heading:
            text = f"\n## {text}\n"
        self._chunks.append(text)

    def text(self) -> str:
        self._flush()
        # Dedupe consecutive identical lines (menus render twice in some pages).
        out: list[str] = []
        for line in self._chunks:
            if not out or out[-1] != line:
                out.append(line)
        return "\n".join(out)


def _looks_like_boilerplate(line: str) -> bool:
    low = line.strip().lower()
    if len(low) <= 2:
        return True
    junk_exact = {
        "skip to main content", "home", "search", "menu", "newsletters", "subscribe",
        "english", "français", "русский", "español", "عربي", "中文",
        "footer", "breadcrumb", "navigation", "cookies", "privacy policy",
        "sections", "on this page", "feedback", "print", "share", "download",
        "related", "more", "see also", "back to top",
    }
    if low in junk_exact:
        return True
    # Nav crumbs / social links / bare link lists.
    if re.fullmatch(r"(twitter|x|facebook|linkedin|instagram|youtube|tiktok|snapchat|rss|©.*|all rights reserved.*)", low):
        return True
    return False


_INLINE_JUNK = ("Skip to main content", "Skip to main text")

# WHO fact sheets end their real content with the "WHO response" section; what
# follows is related-links litter (other fact sheets, news, courses). Cut at the
# first of these markers found in the LAST quarter of the file only.
_WHO_TAIL_MARKERS = ("Fact sheets", "News", "Related", "More about", "Feature stories")


def _trim_source_specific(name: str, lines: list[str]) -> list[str]:
    if name == "gpl-faq":
        # The FAQ page opens with site nav plus a full table of contents that
        # duplicates every question as a bare line - a retrieval hazard (a
        # chunk of question-only lines can outrank the actual answers). Body
        # entries are distinguishable: each carries its anchor, "( #Anchor )".
        for i, ln in enumerate(lines):
            if re.search(r"\( #\w+ \)", ln):
                return lines[i:]
    if name.startswith("who-"):
        floor = int(len(lines) * 0.75)
        for i in range(floor, len(lines)):
            if lines[i].strip().lstrip("# ").rstrip() in _WHO_TAIL_MARKERS:
                return lines[:i]
    return lines


def convert_html(path: Path) -> str:
    parser = _TextExtractor()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    lines = []
    for ln in parser.text().splitlines():
        for junk in _INLINE_JUNK:
            ln = ln.replace(junk, "")
        if not _looks_like_boilerplate(ln):
            lines.append(ln)
    lines = _trim_source_specific(path.stem, lines)
    return "\n".join(lines).strip() + "\n"


def convert_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "") for page in reader.pages]
    text = "\n\n".join(pages)
    # Strip embedded XMP packets if any leak through (article-05 Bug 3 defense).
    text = re.sub(r"<\?xpacket.*?\?>", "", text, flags=re.DOTALL)
    return text.strip() + "\n"


def main() -> None:
    # SEPA is the fourth topic: its sources are the production rulebook PDFs
    # already in corpus/raw/ (gitignored, fetched per README). Mirror them into
    # the uniform topic layout so the matrix harness reads all topics alike.
    sepa_raw = TOPICS / "sepa" / "raw"
    sepa_raw.mkdir(parents=True, exist_ok=True)
    for pdf in Path("corpus/raw").glob("*.pdf"):
        dest = sepa_raw / pdf.name
        if not dest.exists():
            dest.write_bytes(pdf.read_bytes())

    for topic_dir in sorted(TOPICS.iterdir()):
        if not topic_dir.is_dir():
            continue
        raw_dir = topic_dir / "raw"
        raw_dir.mkdir(exist_ok=True)
        # Sources may sit at the topic root (first run) or already in raw/ (rerun).
        sources = [p for d in (topic_dir, raw_dir) for p in sorted(d.iterdir())
                   if p.is_file() and p.suffix.lower() in {".html", ".pdf"}]
        for src in sources:
            out = topic_dir / (src.stem + ".txt")
            if src.suffix.lower() == ".html":
                out.write_text(convert_html(src), encoding="utf-8")
            else:
                out.write_text(convert_pdf(src), encoding="utf-8")
            if src.parent != raw_dir:
                src = src.replace(raw_dir / src.name)
            words = len(out.read_text(encoding="utf-8").split())
            print(f"{topic_dir.name}/{out.name}: {words} words")


if __name__ == "__main__":
    main()
