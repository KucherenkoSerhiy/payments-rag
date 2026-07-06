"""Command-line entry for the corpus: index it, query it, inspect it.

    uv run python -m payments_rag.cli index [--reset] [--corpus DIR]
    uv run python -m payments_rag.cli query "how fast does SCT Inst settle?" [-k 5]
    uv run python -m payments_rag.cli stats
    uv run python -m payments_rag.cli reset

`query` is the Week-2 checkpoint: it prints the retrieved spec passages with
source + page. No answer generation yet — that is Week 3.
"""

from __future__ import annotations

import argparse
import logging
import textwrap

from payments_rag.adapters import db
from payments_rag.indexing.indexer import CorpusIndexer
from payments_rag.orchestrator import answer as answer_question
from payments_rag.retrieval.retriever import retrieve

log = logging.getLogger("payments_rag")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_index(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        if args.reset:
            cleared = db.clear_all(conn)
            conn.commit()
            log.info("reset: cleared %d existing chunks", cleared)
        indexer = CorpusIndexer(
            conn, chunk_size=args.chunk_size, overlap=args.overlap
        )
        stats = indexer.index_corpus(args.corpus)
        total = sum(s.chunks for s in stats)
        log.info(
            "done: %d document(s), %d chunks (%d rows in table)",
            len(stats),
            total,
            db.count(conn),
        )


def cmd_query(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        results = retrieve(conn, args.question, k=args.k)
    if not results:
        log.info("no results — is the corpus indexed? try: cli index --reset")
        return
    print(f'\nQ: {args.question}\n')
    for rank, r in enumerate(results, 1):
        preview = " ".join(r.text.split())[:240]
        print(f"#{rank}  dist={r.distance:.4f}  {r.source}  p{r.page}")
        print(textwrap.fill(preview, width=100, initial_indent="    ", subsequent_indent="    "))
        print()


def cmd_ask(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        result = answer_question(conn, args.question, k=args.k)
    print(f"\nQ: {args.question}\n")
    print(result.answer)
    print("\nSources:")
    for c in result.citations:
        print(f"  - {c.source} p{c.page}  (chunk {c.chunk_id})")


def cmd_stats(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        total = db.count(conn)
        per_source = db.source_counts(conn)
    log.info("%d chunks across %d source(s):", total, len(per_source))
    for source, n in per_source:
        log.info("  %5d  %s", n, source)


def cmd_reset(args: argparse.Namespace) -> None:
    with db.connect() as conn:
        cleared = db.clear_all(conn)
        conn.commit()
    log.info("cleared %d chunks", cleared)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="payments_rag.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="index the corpus into pgvector")
    p_index.add_argument("--corpus", default="corpus/raw", help="corpus directory")
    p_index.add_argument("--reset", action="store_true", help="clear all chunks first")
    p_index.add_argument("--chunk-size", type=int, default=300, dest="chunk_size")
    p_index.add_argument("--overlap", type=int, default=50)
    p_index.set_defaults(func=cmd_index)

    p_query = sub.add_parser("query", help="retrieve chunks for a question")
    p_query.add_argument("question")
    p_query.add_argument("-k", type=int, default=5, help="how many chunks to return")
    p_query.set_defaults(func=cmd_query)

    p_ask = sub.add_parser("ask", help="answer a question with citations (M3)")
    p_ask.add_argument("question")
    p_ask.add_argument("-k", type=int, default=5, help="chunks to retrieve for context")
    p_ask.set_defaults(func=cmd_ask)

    p_stats = sub.add_parser("stats", help="show chunk counts per source")
    p_stats.set_defaults(func=cmd_stats)

    p_reset = sub.add_parser("reset", help="delete all chunks")
    p_reset.set_defaults(func=cmd_reset)

    return parser


def main(argv: list[str] | None = None) -> None:
    _setup_logging()
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
