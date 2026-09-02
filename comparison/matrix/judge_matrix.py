"""Judge runner: every collected answer scored by all three judges.

Methodology notes, deliberate and load-bearing:

  * The judge prompt is IDENTICAL for all three judges, and none of them uses
    vendor-specific structured output - every judge gets the same plain
    instruction to reply with a JSON object, parsed the same way. Treating
    judges identically is what makes their scores comparable to each other.
  * Every answer is scored by every judge, including the judge from the same
    vendor family as the generator. The same-family cells are not a mistake -
    they ARE the self-preference-bias measurement (compare them to the
    off-diagonal cells). ADR-0007's cross-model rule applies to which score
    you TRUST, not which you measure.
  * Same content-hash resumability as run_matrix (hash covers judge model,
    rubric version, and the answer being judged).

Run after run_matrix:

    PYTHONPATH=. PYTHONIOENCODING=utf-8 python -m comparison.matrix.judge_matrix
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from comparison.logging_setup import get_logger
from comparison.matrix import providers
from comparison.matrix.config import CHAT_MODELS, JUDGES
from comparison.matrix.providers import MissingKeyError

log = get_logger("matrix.judge")

ANSWERS = Path("data/matrix/answers.jsonl")
OUT = Path("data/matrix/judge_scores.jsonl")

RUBRIC_VERSION = "v1"

# Same rubric as evals/judge.py, topic-neutral wording. 0-100, threshold 70
# stays the project-wide pass bar.
JUDGE_PROMPT = """\
You are grading an answer to a question for FACTUAL correctness against a
reference answer. Score 0-100: 100 = fully correct and complete vs the
reference; 0 = wrong or missing the key fact. Ignore wording and style; judge
the facts. Reply with ONLY a JSON object: {{"score": <int>, "critique": "<one sentence>"}}

QUESTION: {question}
REFERENCE: {expected}
CANDIDATE: {actual}
"""


def _parse_grade(text: str) -> tuple[int, str]:
    """Extract {score, critique} from a reply that should be bare JSON.

    Tolerates code fences and stray prose around the object - vendors differ
    in how obediently they emit bare JSON, and normalizing here keeps the
    judging contract identical across all three.
    """
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in judge reply: {text[:200]!r}")
    data = json.loads(match.group(0))
    return int(data["score"]), str(data.get("critique", ""))


def _hash(judge_key: str, answer: str) -> str:
    payload = json.dumps({
        "judge": CHAT_MODELS[judge_key].model_id,
        "rubric": RUBRIC_VERSION,
        "answer": answer,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _write_rows(rows: list[dict]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(OUT)


def _load_existing() -> dict[tuple[str, str, str, str], dict]:
    if not OUT.exists():
        return {}
    rows = {}
    for line in OUT.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[(row["pipeline"], row["topic"], row["question_id"], row["judge"])] = row
    return rows


def run() -> None:
    if not ANSWERS.exists():
        raise FileNotFoundError(f"{ANSWERS} not found - run comparison.matrix.run_matrix first")
    answer_rows = [
        json.loads(line)
        for line in ANSWERS.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    existing = _load_existing()
    out_rows: list[dict] = []
    skipped_judges: set[str] = set()

    for judge_key in JUDGES:
        judge_model = CHAT_MODELS[judge_key]
        for a in answer_rows:
            key = (a["pipeline"], a["topic"], a["question_id"], judge_key)
            cached = existing.get(key)
            if cached and cached.get("content_hash") == _hash(judge_key, a["answer"]):
                out_rows.append(cached)
                continue
            if judge_key in skipped_judges:
                continue
            prompt = JUDGE_PROMPT.format(
                question=a["question"], expected=a["expected_answer"], actual=a["answer"]
            )
            try:
                result = providers.chat(judge_model, prompt)
                score, critique = _parse_grade(result.text)
            except MissingKeyError as e:
                log.warning("SKIP judge %s: %s", judge_key, e)
                skipped_judges.add(judge_key)
                continue
            except ValueError as e:
                log.warning("%s/%s/%s judge=%s: unparseable reply (%s)",
                            a["pipeline"], a["topic"], a["question_id"], judge_key, e)
                continue
            row = {
                "pipeline": a["pipeline"],
                "topic": a["topic"],
                "question_id": a["question_id"],
                "judge": judge_key,
                "score": score,
                "critique": critique,
                "judge_cost_usd": round(
                    providers.chat_cost_usd(judge_model, result.input_tokens, result.output_tokens), 6
                ),
                "content_hash": _hash(judge_key, a["answer"]),
            }
            out_rows.append(row)
            log.info("%s/%s/%s judge=%s: %d", a["pipeline"], a["topic"],
                     a["question_id"], judge_key, score)
            if len(out_rows) % 50 == 0:
                _write_rows(out_rows)  # crash-safety flush

    _write_rows(out_rows)
    print(f"\n{len(out_rows)} judge rows written to {OUT}")
    if skipped_judges:
        print(f"SKIPPED judges (missing API keys): {sorted(skipped_judges)}")


if __name__ == "__main__":
    run()
