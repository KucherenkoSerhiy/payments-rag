# Comparison report

Generated 2026-09-02 by `python -m comparison.report` from
`data/comparison/ragas_scores.jsonl` and `judge_scores.jsonl`. Do not edit by
hand - rerun instead. Ordered by judge score, the primary metric.

| System | n | Judge (0-100) | Pass >=70 | Faithfulness | Relevancy | Precision | Recall | Cost (10 q) | Latency |
|---|---|---|---|---|---|---|---|---|---|
| llamaindex | 10 | 96.5 | 100% | 1.000 | 0.903 | 0.807 | 1.000 | $0.0341 | 1.45s |
| notebooklm | 10 | 92.5 | 100% | - | 0.903 | - | - | $0.0000 | 15.00s |
| openai-file-search | 10 | 90.2 | 90% | 0.925 | 0.849 | 0.908 | 0.750 | $0.3526 | 6.20s |
| payments-rag | 10 | 84.8 | 90% | 0.991 | 0.847 | 0.853 | 0.900 | $0.0276 | 2.68s |
| haystack | 10 | 76.5 | 80% | 0.975 | 0.719 | 0.660 | 0.817 | $0.0413 | 3.23s |
| langchain | 10 | 71.5 | 70% | 0.925 | 0.736 | 0.629 | 0.700 | $0.0328 | 1.55s |

Notes:
- notebooklm's faithfulness/precision/recall are `-`, not zero: its UI exposes
  only cited filenames, so those metrics score noise (see comparison/collect/notebooklm.py).
  Its latency is an operator-observed approximation and its cost excludes ~11 min
  of manual setup.
- Judge = cross-model factual correctness vs the golden reference (evals/judge.py).
  RAGAS columns = mechanics: grounding, topicality, retrieval precision/recall.
