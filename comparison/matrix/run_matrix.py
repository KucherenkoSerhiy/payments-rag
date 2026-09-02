"""Collection runner: every pipeline x every topic x every golden question.

Resumable the way article 05's scorers ended up (the hard way - see
docs/incidents/2026-08-29): each row carries a `content_hash` of everything
that determines the answer (embed model, chat model, prompt version, corpus
fingerprint, question text). A cached row is reused only when its hash still
matches, so changing a model id, the prompt, or the corpus automatically
invalidates exactly the affected rows. The scoring-engine-version gap that
bit the RAGAS upgrade is covered too: PROMPT_VERSION is part of the hash -
bump it when the answering contract changes.

Pipelines whose provider keys are missing are SKIPPED with a loud warning,
not failed: the matrix can run partially while remaining keys are pending.

Run (main venv, no isolation needed - no new deps):

    PYTHONPATH=. PYTHONIOENCODING=utf-8 python -m comparison.matrix.run_matrix
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from comparison.logging_setup import get_logger
from comparison.matrix.config import CHAT_MODELS, EMBED_MODELS, PIPELINES, TOPICS
from comparison.matrix.corpus import fingerprint
from comparison.matrix.pipeline import ANSWER_PROMPT, IndexedTopic
from comparison.matrix.providers import MissingKeyError

log = get_logger("matrix.run")

GOLDEN_DIR = Path("comparison/matrix/golden")
OUT = Path("data/matrix/answers.jsonl")

PROMPT_VERSION = "v1"  # bump when ANSWER_PROMPT or retrieval settings change


def _load_golden(topic: str) -> list[dict]:
    entries = yaml.safe_load((GOLDEN_DIR / f"{topic}.yaml").read_text(encoding="utf-8"))
    return list(entries)


def _content_hash(pipeline_key: str, topic: str, corpus_fp: str, question: str) -> str:
    from comparison.matrix.config import PIPELINES as _p
    pipe = next(p for p in _p if p.key == pipeline_key)
    payload = json.dumps({
        "embed": EMBED_MODELS[pipe.embed].model_id,
        "chat": CHAT_MODELS[pipe.chat].model_id,
        "prompt": PROMPT_VERSION,
        "prompt_text_hash": hashlib.sha256(ANSWER_PROMPT.encode()).hexdigest()[:8],
        "corpus": corpus_fp,
        "question": question,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _write_rows(rows: list[dict]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(OUT)


def _load_existing() -> dict[tuple[str, str, str], dict]:
    if not OUT.exists():
        return {}
    rows = {}
    for line in OUT.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[(row["pipeline"], row["topic"], row["question_id"])] = row
    return rows


def run() -> None:
    existing = _load_existing()
    all_rows: list[dict] = []
    skipped_pipelines: list[str] = []

    for pipe in PIPELINES:
        for topic in TOPICS:
            corpus_fp = fingerprint(topic)
            golden = _load_golden(topic)
            needed = [
                g for g in golden
                if (cached := existing.get((pipe.key, topic, g["id"]))) is None
                or cached.get("content_hash") != _content_hash(pipe.key, topic, corpus_fp, g["question"])
            ]
            # Reuse every still-valid cached row.
            for g in golden:
                cached = existing.get((pipe.key, topic, g["id"]))
                if cached and cached.get("content_hash") == _content_hash(
                    pipe.key, topic, corpus_fp, g["question"]
                ):
                    all_rows.append(cached)

            if not needed:
                log.info("%s/%s: all %d cached", pipe.key, topic, len(golden))
                continue

            try:
                indexed = IndexedTopic(pipe, topic)
            except MissingKeyError as e:
                log.warning("SKIP %s (all topics): %s", pipe.key, e)
                skipped_pipelines.append(pipe.key)
                break  # no point trying the other topics of this pipeline

            for g in needed:
                try:
                    ans = indexed.answer(g["question"])
                except MissingKeyError as e:
                    log.warning("SKIP %s mid-run: %s", pipe.key, e)
                    skipped_pipelines.append(pipe.key)
                    break
                row = {
                    "pipeline": pipe.key,
                    "topic": topic,
                    "question_id": g["id"],
                    "question": g["question"],
                    "expected_answer": g["expected_answer"],
                    "answer": ans.answer,
                    "contexts": ans.contexts,
                    "sources": ans.sources,
                    "latency_s": ans.latency_s,
                    "cost_usd": ans.cost_usd,
                    "index_cost_usd": round(indexed.index_cost_usd, 6),
                    "content_hash": _content_hash(pipe.key, topic, corpus_fp, g["question"]),
                }
                all_rows.append(row)
                log.info("%s/%s/%s: %.2fs $%.4f", pipe.key, topic, g["id"],
                         ans.latency_s, ans.cost_usd)

            # Flush after every (pipeline, topic) cell: a crash mid-run must
            # never cost the answers already paid for - resumability is only
            # real if partial progress reaches disk.
            _write_rows(all_rows)

    _write_rows(all_rows)

    print(f"\n{len(all_rows)} answer rows written to {OUT}")
    if skipped_pipelines:
        print(f"SKIPPED (missing API keys): {sorted(set(skipped_pipelines))}")


if __name__ == "__main__":
    run()
