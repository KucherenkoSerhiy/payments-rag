"""Tests for Reciprocal Rank Fusion — your target to make green. Pure, no I/O."""

from __future__ import annotations

from payments_rag.fusion import reciprocal_rank_fusion


def test_single_list_preserves_order() -> None:
    # scores strictly decrease with rank, so order is unchanged
    assert reciprocal_rank_fusion([[3, 1, 2]]) == [3, 1, 2]


def test_all_unique_ids_are_kept_and_deduped() -> None:
    fused = reciprocal_rank_fusion([[1, 2], [2, 3]])
    assert set(fused) == {1, 2, 3}
    assert len(fused) == 3  # 2 appears in both lists but only once in the result


def test_agreement_across_lists_wins() -> None:
    # 1 is rank 1 in both lists -> highest combined score -> first
    assert reciprocal_rank_fusion([[1, 2, 3], [1, 4, 5]])[0] == 1


def test_two_mid_ranks_beat_one_top_rank() -> None:
    # id 2 is rank 2 in both lists: 1/62 + 1/62 ≈ 0.0323
    # id 3 is rank 1 in one list:   1/61       ≈ 0.0164
    fused = reciprocal_rank_fusion([[9, 2], [3, 2]])
    assert fused.index(2) < fused.index(3)


def test_empty_inputs() -> None:
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[]]) == []


# --- discriminating tests: these FAIL for "concatenate + dedup", pass for RRF ---

def test_agreement_outranks_an_earlier_single_list_id() -> None:
    # 9 is rank 1 in the first list; 2 is rank 2 in BOTH lists.
    # concat+dedup would put 9 first (it appears first); RRF puts 2 first:
    #   2 -> 1/62 + 1/62 = 0.0323   vs   9 -> 1/61 = 0.0164
    assert reciprocal_rank_fusion([[9, 2], [3, 2]])[0] == 2


def test_full_order_follows_rrf_score() -> None:
    # scores for [[1, 2], [2, 3]]:
    #   2 -> 1/62 + 1/61 = 0.0325   (in both lists)
    #   1 -> 1/61        = 0.0164
    #   3 -> 1/62        = 0.0161
    # concat+dedup would give [1, 2, 3]; RRF gives:
    assert reciprocal_rank_fusion([[1, 2], [2, 3]]) == [2, 1, 3]
