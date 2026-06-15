"""Generate a synthetic SEPA fixture PDF for the step-4 spike.

NOT a real spec — a labelled stand-in so step4 can prove the read->chunk->
embed->store->retrieve path without downloading anything. Real SEPA / ISO 20022
PDFs go in corpus/raw/ (gitignored) for the Week-2 corpus.

Writes a minimal one-page text PDF with exact xref offsets (no deps).
"""

from __future__ import annotations

from pathlib import Path

OUT = Path("corpus/raw/sample_sepa.pdf")

# A page of SEPA-ish prose. Several sentences so the word-window chunker
# produces more than one chunk.
LINES = [
    "SEPA Credit Transfer (SCT) and SCT Instant Rulebook - synthetic fixture.",
    "An SCT Inst transaction is executed within ten seconds at any time of day,",
    "every day of the year, including weekends and public holidays. The maximum",
    "amount per SCT Inst transaction is defined by the scheme and may be raised",
    "by agreement between payment service providers. A standard SCT is not",
    "instant: funds are made available to the beneficiary by the next business",
    "day at the latest. Both schemes use ISO 20022 messages. The pacs.008 message",
    "carries a customer credit transfer between the originator and beneficiary",
    "banks, while pacs.002 reports the status of a previously submitted payment.",
    "A pacs.004 payment return is used to send funds back when settlement cannot",
    "complete. The BIC identifies the financial institution within the SEPA area,",
    "and the IBAN identifies the specific account of the customer being credited.",
]


def _escape(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _content_stream() -> bytes:
    parts = ["BT", "/F1 11 Tf", "72 720 Td", "14 TL"]
    for i, line in enumerate(LINES):
        # first line uses Td above; subsequent lines drop one leading via T*
        if i == 0:
            parts.append(f"({_escape(line)}) Tj")
        else:
            parts.append("T*")
            parts.append(f"({_escape(line)}) Tj")
    parts.append("ET")
    return ("\n".join(parts) + "\n").encode("latin-1")


def build() -> bytes:
    content = _content_stream()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_pos = len(out)
    n = len(objects) + 1
    out += f"xref\n0 {n}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size " + str(n).encode() + b" /Root 1 0 R >>\n"
        b"startxref\n" + str(xref_pos).encode() + b"\n%%EOF\n"
    )
    return bytes(out)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(build())
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
