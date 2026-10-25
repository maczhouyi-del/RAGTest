"""Generation contract; selecting a provider never changes the embedding space."""

from typing import Callable, Protocol


class GenerationProvider(Protocol):
    fingerprint: dict
    cancel_check: Callable[[], None] | None

    def generate(self, task: str, data: dict) -> dict: ...
    def close(self) -> None: ...
