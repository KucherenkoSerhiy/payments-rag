"""Spike step 2 — one raw Claude API call, response printed.

No framework. Just the anthropic SDK and a single messages.create call.
"""

from __future__ import annotations

from anthropic import Anthropic

from payments_rag import config
from spike._log import setup

log = setup()

QUESTION = "In one sentence, what is the difference between SEPA SCT and SCT Inst?"


def main() -> None:
    client = Anthropic(api_key=config.require_anthropic_key())
    log.info("calling %s ...", config.LLM_MODEL)

    resp = client.messages.create(
        model=config.LLM_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": QUESTION}],
    )

    answer = "".join(block.text for block in resp.content if block.type == "text")
    log.info("Q: %s", QUESTION)
    log.info("A: %s", answer)
    log.info(
        "tokens: in=%s out=%s",
        resp.usage.input_tokens,
        resp.usage.output_tokens,
    )
    log.info("STEP 2 OK — Claude API call verified")


if __name__ == "__main__":
    main()
