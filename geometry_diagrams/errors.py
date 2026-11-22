"""Public exceptions raised by the generation strategies.

Kept free of heavy imports so it is cheap to import from anywhere."""
from __future__ import annotations


class GenerationFailedError(RuntimeError):
    """A strategy used up its attempts without producing a diagram.

    Subclasses RuntimeError, with the same message the strategies always raised, so
    existing `except RuntimeError` handlers keep working. The usage fields are what
    the failed run spent: they are real money even though no diagram came back.
    `cost_usd` is None when no call reported a cost (unknown, not free).
    """

    def __init__(
        self,
        strategy: str,
        attempts: int,
        last_error: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float | None = None,
    ) -> None:
        super().__init__(f"{strategy} failed after {attempts} attempts. Last error: {last_error}")
        self.strategy = strategy
        self.attempts = attempts
        self.last_error = last_error
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cost_usd = cost_usd
