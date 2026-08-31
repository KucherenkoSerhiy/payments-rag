"""One logger for the whole comparison run.

Every adapter call, every score, every skip gets a line here, not a print().
This run is meant to be reported on later, so the log is the receipt: what was
asked, what came back, what it cost, when. See `data/comparison/run.log`.
"""

from __future__ import annotations

import logging
from pathlib import Path

LOG_DIR = Path("data/comparison")


def get_logger(name: str) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:  # idempotent: re-importing must not double-attach handlers
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")

    file_handler = logging.FileHandler(LOG_DIR / "run.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)
    return logger
