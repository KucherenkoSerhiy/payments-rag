"""Fetch the article-06 topic corpora (licenses, agentic, nutrition) from their
original public sources into corpus/topics/<topic>/.

The fetched content is deliberately NOT committed (see .gitignore): the sources
carry their own licenses (WHO copyright, GNU pages are CC BY-ND, vendor PDFs).
This script + scripts/convert_topic_corpus.py make the corpus reproducible
without redistributing it. Run both, in order, from the repo root:

    PYTHONIOENCODING=utf-8 python scripts/fetch_topic_corpus.py
    PYTHONIOENCODING=utf-8 python scripts/convert_topic_corpus.py

Stdlib-only (urllib), no new dependencies.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

TOPICS = Path("corpus/topics")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

SPDX = "https://raw.githubusercontent.com/spdx/license-list-data/main/text"
WHO = "https://www.who.int/news-room/fact-sheets/detail"

# (topic, filename, url) - filenames must match what convert_topic_corpus.py
# and the golden sets (comparison/matrix/golden/*.yaml) reference.
SOURCES: list[tuple[str, str, str]] = [
    ("licenses", "GPL-3.0-only.txt", f"{SPDX}/GPL-3.0-only.txt"),
    ("licenses", "AGPL-3.0-only.txt", f"{SPDX}/AGPL-3.0-only.txt"),
    ("licenses", "Apache-2.0.txt", f"{SPDX}/Apache-2.0.txt"),
    ("licenses", "MIT.txt", f"{SPDX}/MIT.txt"),
    ("licenses", "BSD-3-Clause.txt", f"{SPDX}/BSD-3-Clause.txt"),
    ("licenses", "MPL-2.0.txt", f"{SPDX}/MPL-2.0.txt"),
    ("licenses", "gpl-faq.html", "https://www.gnu.org/licenses/gpl-faq.html"),
    ("agentic", "anthropic-building-effective-agents.html",
     "https://www.anthropic.com/engineering/building-effective-agents"),
    ("agentic", "openai-practical-guide-agents.pdf",
     "https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf"),
    ("agentic", "langgraph-overview.md",
     "https://docs.langchain.com/oss/python/langgraph/overview.md"),
    ("agentic", "langgraph-workflows-agents.md",
     "https://docs.langchain.com/oss/python/langgraph/workflows-agents.md"),
    ("nutrition", "who-healthy-diet.html", f"{WHO}/healthy-diet"),
    ("nutrition", "who-salt-reduction.html", f"{WHO}/salt-reduction"),
    ("nutrition", "who-obesity-overweight.html", f"{WHO}/obesity-and-overweight"),
    ("nutrition", "who-physical-activity.html", f"{WHO}/physical-activity"),
    ("nutrition", "who-trans-fat.html", f"{WHO}/trans-fat"),
    ("nutrition", "who-diabetes.html", f"{WHO}/diabetes"),
    ("nutrition", "who-hypertension.html", f"{WHO}/hypertension"),
]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def main() -> None:
    for topic, name, url in SOURCES:
        # Raw HTML/PDF sources live under raw/ once converted; fetch straight there.
        dest_dir = TOPICS / topic / ("raw" if name.endswith((".html", ".pdf")) else "")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / name
        if dest.exists():
            print(f"skip (exists): {dest}")
            continue
        data = fetch(url)
        dest.write_bytes(data)
        print(f"fetched {dest} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
