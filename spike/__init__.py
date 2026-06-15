"""W1 spike: prove every external integration before building the real pipeline.

Run each step from the repo root:
    uv run python -m spike.step1_db
    uv run python -m spike.step2_llm
    uv run python -m spike.step3_embed
    uv run python -m spike.step4_pdf  path/to/sepa.pdf
"""
