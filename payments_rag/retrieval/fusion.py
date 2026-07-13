"""Reciprocal Rank Fusion: merge several ranked id-lists into one.

YOUR TASK: implement `reciprocal_rank_fusion`. It's a pure function (ids in,
ids out, no DB, no API), so tests/test_fusion.py checks it directly.

Why it exists: hybrid retrieval produces two ranked lists (semantic + keyword)
whose *scores* live on different scales and can't be added. RRF fuses them using
only rank *position*: each id scores sum(1 / (k0 + rank)) over the lists it
appears in (rank is 1-based; k0 dampens the top so no single list dominates).
Ids that rank well in BOTH lists rise to the top.
"""

from __future__ import annotations

from collections import defaultdict


def reciprocal_rank_fusion(ranked_lists: list[list[int]], *, k0: int = 60) -> list[int]:
    """Fuse ranked id-lists into one, best-first."""
    scores: dict[int, float] = defaultdict(float)
    for ranked_list in ranked_lists:
        for index, cid in enumerate(ranked_list):
            scores[cid] += 1 / (k0 + index + 1)
    return sorted(scores, key=lambda cid: scores[cid], reverse=True)
