"""RAGAS metrics: faithfulness, answer relevancy, context precision, context
recall, computed uniformly for any system's answer. See `docs/vs-managed-rag.md`
for why RAGAS: it fills the gap the hand-built judge (`evals/judge.py`) leaves,
since that judge grades correctness against a reference, not whether the answer
was actually grounded in what was retrieved.

RAGAS hard-requires langchain (`langchain`, `langchain-core`,
`langchain-community`, `langchain_openai`) as unconditional dependencies, not an
extra, and this project stays langchain-free (ADR-0004). So this module is
NEVER imported from the main venv, and is NOT a project dependency in
pyproject.toml. Run it isolated, always:

    uv run --isolated --with "ragas==0.4.3" --with "langchain-community<0.3" \\
        --with langchain-openai --with python-dotenv \\
        python -m evals.ragas_metrics

Two facts pinned here on purpose, both verified by hand against the currently
installed package (ragas 0.4.3, the latest release as of 2026-08-30), not
assumed from docs or an older run:

1. `langchain-community<0.3` works around a real, live bug: plain `import ragas`
   crashes with `ModuleNotFoundError: No module named
   'langchain_community.chat_models.vertexai'`, reproduced directly against a
   fresh, unpinned `ragas` install. Root cause: `ragas/llms/base.py`
   unconditionally imports that path, which modern langchain-community (>=0.3)
   removed. Confirmed still open and unfixed on the vendor's side:
   https://github.com/vibrantlabsai/ragas/issues/2753 (open), fix pending at
   https://github.com/vibrantlabsai/ragas/pull/2837 (unmerged).
2. `LangchainLLMWrapper`/`LangchainEmbeddingsWrapper` are what this module uses
   for the LLM/embeddings, confirmed working end-to-end (real, non-NaN scores)
   against 0.4.3. They print a deprecation warning pointing at
   `llm_factory`/`embedding_factory` instead; not switched, since the
   deprecated pair is the one verified to work with these four metric classes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas import SingleTurnSample, evaluate
from ragas.dataset_schema import EvaluationDataset
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    Faithfulness,
    LLMContextPrecisionWithoutReference,
    LLMContextRecall,
    ResponseRelevancy,
)

load_dotenv()

# Matches evals/judge.py's cross-model judge (ADR-0007): GPT-4o, a different
# vendor from the Claude-produced payments-rag answers. This is NOT a different
# vendor from OpenAI's own file_search answers, so RAGAS scores on that one
# system carry the same-vendor caveat this project's own eval philosophy warns
# about; the comparison report says so explicitly rather than hiding it.
JUDGE_MODEL = "gpt-4o"
EMBED_MODEL = "text-embedding-3-small"


@dataclass
class RagasScore:
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    context_recall: float


def _wrappers() -> tuple[LangchainLLMWrapper, LangchainEmbeddingsWrapper]:
    key = os.environ["OPENAI_API_KEY"]
    llm = LangchainLLMWrapper(ChatOpenAI(model=JUDGE_MODEL, api_key=key))
    emb = LangchainEmbeddingsWrapper(OpenAIEmbeddings(model=EMBED_MODEL, api_key=key))
    return llm, emb


def score_one(question: str, contexts: list[str], answer: str, ground_truth: str) -> RagasScore:
    llm, emb = _wrappers()
    sample = SingleTurnSample(
        user_input=question,
        retrieved_contexts=contexts or [""],  # RAGAS requires a non-empty list
        response=answer,
        reference=ground_truth,
    )
    dataset = EvaluationDataset(samples=[sample])
    metrics = [Faithfulness(), ResponseRelevancy(), LLMContextPrecisionWithoutReference(), LLMContextRecall()]
    result = evaluate(dataset, metrics=metrics, llm=llm, embeddings=emb, show_progress=False)
    row = result.to_pandas().iloc[0]
    return RagasScore(
        faithfulness=float(row["faithfulness"]),
        answer_relevancy=float(row["answer_relevancy"]),
        context_precision=float(row["llm_context_precision_without_reference"]),
        context_recall=float(row["context_recall"]),
    )
