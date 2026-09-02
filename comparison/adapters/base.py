"""Contract for the framework comparators: each adapter module exposes
`build(pdf_paths) -> RagSystem`, so one collector (comparison.collect.framework)
drives all of them. The non-framework systems keep their own collectors."""

from __future__ import annotations

from typing import Protocol

from comparison.schema import SystemAnswer


class RagSystem(Protocol):
    def answer(self, question_id: str, question: str, ground_truth: str) -> SystemAnswer:
        """Answer one golden-set question, normalized to the shared shape."""
        ...
