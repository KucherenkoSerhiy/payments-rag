"""Shared logging setup for spike scripts (logger, not print — per CLAUDE.md)."""

from __future__ import annotations

import logging


def setup() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger("spike")
