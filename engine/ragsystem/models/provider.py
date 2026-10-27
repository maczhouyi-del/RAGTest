"""Generation contract; selecting a provider never changes the embedding space."""

from typing import Callable, Protocol

EVIDENCE_ANSWER_RULES = (
    "Assess all supplied current excerpts. If sources conflict, explicitly describe the conflict "
    "with citations to both sides; never silently select only a favorable result. "
    "Preserve experimental conditions, uncertainty and comparability limits. "
    "If the excerpts cannot answer the question, return empty claims. "
)


class GenerationProvider(Protocol):
    fingerprint: dict
    cancel_check: Callable[[], None] | None

    def generate(self, task: str, data: dict) -> dict: ...
    def close(self) -> None: ...
