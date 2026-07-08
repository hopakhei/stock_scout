"""Hard cost guard for LLM usage in a single run (NFR-3 / FR-6.3)."""

from __future__ import annotations

# USD per million tokens (input, output). Update when Anthropic pricing changes.
PRICES = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-5": (3.00, 15.00),
}
DEFAULT_PRICE = (3.00, 15.00)


class BudgetExceeded(Exception):
    pass


class Budget:
    def __init__(self, cap_usd: float):
        self.cap_usd = cap_usd
        self.spent_usd = 0.0

    def record(self, model: str, input_tokens: int, output_tokens: int) -> None:
        pin, pout = PRICES.get(model, DEFAULT_PRICE)
        self.spent_usd += (input_tokens * pin + output_tokens * pout) / 1_000_000

    def check(self) -> None:
        if self.spent_usd >= self.cap_usd:
            raise BudgetExceeded(f"LLM budget exhausted: ${self.spent_usd:.3f} >= ${self.cap_usd}")
