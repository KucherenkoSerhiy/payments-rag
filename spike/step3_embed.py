"""Spike step 3 — embed sentences, store in pgvector, retrieve nearest neighbour.

Proves the full shared path: text -> embedding (pinned model) -> pgvector ->
similarity search returns the semantically closest stored sentence.
"""

from __future__ import annotations

from payments_rag import db
from payments_rag.embedding import embed, embed_one
from spike._log import setup

log = setup()

SOURCE = "spike-step3"

# A few payments sentences to retrieve against.
SENTENCES = [
    "SCT Inst settles a SEPA credit transfer within ten seconds, around the clock.",
    "A pacs.008 message carries a customer credit transfer between banks.",
    "A pacs.004 message is used to return funds for a payment.",
    "The BIC identifies a financial institution in the SEPA scheme.",
]

QUERY = "How fast is an instant SEPA payment?"


def main() -> None:
    with db.connect() as conn:
        db.delete_source(conn, SOURCE)  # idempotent re-runs

        vectors = embed(SENTENCES)
        log.info("embedded %d sentences, dim=%d", len(vectors), len(vectors[0]))
        for i, (text, vec) in enumerate(zip(SENTENCES, vectors)):
            db.insert_chunk(conn, source=SOURCE, chunk_index=i, text=text, embedding=vec)
        conn.commit()
        log.info("stored %d chunks (total in table: %d)", len(SENTENCES), db.count(conn))

        qvec = embed_one(QUERY)
        results = db.nearest(conn, qvec, k=3)

        log.info("query: %s", QUERY)
        for rank, (cid, source, text, _page, dist) in enumerate(results, 1):
            log.info("  #%d  dist=%.4f  id=%d  %s", rank, dist, cid, text)

        top_text = results[0][2]
        assert "ten seconds" in top_text, f"unexpected nearest neighbour: {top_text}"
        log.info("STEP 3 OK — nearest neighbour is the instant-settlement sentence")


if __name__ == "__main__":
    main()
