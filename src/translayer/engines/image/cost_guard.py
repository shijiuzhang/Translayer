"""Explicit cost guard for paid whole-image localization providers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ImageAPICostGuard:
    enabled: bool = False
    max_calls: int = 0
    max_cost_usd: float = 0.0
    estimated_cost_per_call_usd: float = 0.08
    calls_reserved: int = 0

    @property
    def estimated_spend_usd(self) -> float:
        return self.calls_reserved * self.estimated_cost_per_call_usd

    def reserve(self) -> None:
        if not self.enabled:
            raise RuntimeError(
                "Paid image API calls are disabled. Run the local image plan first, then "
                "explicitly enable a bounded budget."
            )
        next_calls = self.calls_reserved + 1
        next_cost = next_calls * self.estimated_cost_per_call_usd
        if self.max_calls <= 0 or next_calls > self.max_calls:
            raise RuntimeError(
                f"Paid image API call limit reached ({self.calls_reserved}/{self.max_calls})."
            )
        if self.max_cost_usd <= 0 or next_cost > self.max_cost_usd + 1e-9:
            raise RuntimeError(
                f"Paid image API budget exceeded: estimated ${next_cost:.2f} > "
                f"${self.max_cost_usd:.2f}."
            )
        self.calls_reserved = next_calls
