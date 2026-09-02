"""Model-matrix experiment (article 06): what varies, what is frozen.

Article 05 varied the FRAMEWORK with models held constant; this experiment
inverts it - one fixed hand-rolled pipeline (chunk -> embed -> retrieve ->
generate), with the embedding and generation models as the only variables.
Every pipeline below differs from some other pipeline by exactly one
component, so every comparison is single-variable.

Prices are list prices per 1M tokens, collected 2026-09-01 from vendor pages
and pricing aggregators. Vendors cut prices repeatedly through 2026 -
RE-VERIFY against each vendor's live pricing page before publishing any
dollar figure derived from these constants.

Model IDs marked TODO(verify) have not yet been confirmed against the live
API (the smoke test does that; some need API keys that don't exist yet).
"""

from __future__ import annotations

from dataclasses import dataclass

# --- retrieval knobs, frozen (match article 05's standardization) -----------

CHUNK_WORDS = 200        # the article-05 anchor (Haystack's documented default)
CHUNK_OVERLAP_WORDS = 20  # same ~10% ratio as 05
TOP_K = 5                 # matches payments-rag's orchestrator.answer(k=5)

TOPICS = ("sepa", "licenses", "agentic", "nutrition")


# --- providers ---------------------------------------------------------------

@dataclass(frozen=True)
class EmbedModel:
    key: str        # short name used in pipeline ids and result rows
    provider: str   # openai | voyage | gemini
    model_id: str
    price_per_mtok: float  # input tokens (embeddings have no output tokens)


@dataclass(frozen=True)
class ChatModel:
    key: str
    provider: str   # openai | anthropic | gemini | deepseek
    model_id: str
    price_in_per_mtok: float
    price_out_per_mtok: float


EMBED_MODELS = {
    "oai-small": EmbedModel("oai-small", "openai", "text-embedding-3-small", 0.02),
    "voyage-4": EmbedModel("voyage-4", "voyage", "voyage-4", 0.06),
    "gem-emb": EmbedModel("gem-emb", "gemini", "gemini-embedding-001", 0.15),
}

CHAT_MODELS = {
    "sonnet": ChatModel("sonnet", "anthropic", "claude-sonnet-5", 2.00, 10.00),
    "haiku": ChatModel("haiku", "anthropic", "claude-haiku-4-5-20251001", 1.00, 5.00),
    # Model ids confirmed live against the API 2026-09-01 (models.list + one
    # real completion each); prices still need the pre-publication re-check.
    "gpt-terra": ChatModel("gpt-terra", "openai", "gpt-5.6-terra", 2.00, 12.00),
    "gpt-sol": ChatModel("gpt-sol", "openai", "gpt-5.6-sol", 4.00, 24.00),
    # TODO(verify): Gemini 3.7 Flash API id + intro pricing (released 2026-08-13).
    "gem-flash": ChatModel("gem-flash", "gemini", "gemini-3.7-flash", 0.75, 3.75),
    # DeepSeek serves its latest V-series under the stable "deepseek-chat" alias.
    # TODO(verify): peak/off-peak UTC pricing introduced mid-2026 - price varies.
    "deepseek": ChatModel("deepseek", "deepseek", "deepseek-chat", 0.44, 0.87),
}


# --- the matrix --------------------------------------------------------------

@dataclass(frozen=True)
class Pipeline:
    key: str
    embed: str  # EMBED_MODELS key
    chat: str   # CHAT_MODELS key
    note: str   # what this pipeline isolates (single-variable vs which other)
    # True for a deliberately cross-stack entry: BOTH components differ from
    # every other pipeline, so its results compare stacks, never a single
    # component. Exactly one such entry exists (p5); everything else must have
    # a single-variable partner (tests enforce it).
    cross_stack: bool = False


PIPELINES = (
    Pipeline("p1-oai-sonnet", "oai-small", "sonnet",
             "baseline: today's production payments-rag pairing"),
    Pipeline("p2-oai-haiku", "oai-small", "haiku",
             "haiku vs sonnet, embedder held constant (vs p1)"),
    Pipeline("p3-oai-gpt", "oai-small", "gpt-terra",
             "OpenAI-native stack (vs p1: generator swapped)"),
    Pipeline("p4-voyage-sonnet", "voyage-4", "sonnet",
             "Anthropic-recommended embedder (vs p1: embedder swapped)"),
    Pipeline("p5-gem-gem", "gem-emb", "gem-flash",
             "Google-native stack - whole-stack comparison only", cross_stack=True),
    Pipeline("p6-oai-deepseek", "oai-small", "deepseek",
             "cost-outlier wildcard (vs p1/p3: generator swapped)"),
)

# Judges: every answer is scored by all three - one per vendor family. Since
# generators span the same three families, self-preference falls out for free:
# the same-vendor judge/generator cells are the self-judging measurement,
# no extra runs needed. Cross-model judging (ADR-0007) = read the off-diagonal.
JUDGES = ("sonnet", "gpt-sol", "gem-flash")

# Which env var carries each provider's key (.env / environment).
PROVIDER_ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "voyage": "VOYAGE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}
