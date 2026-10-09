"""CostEstimator. Unknown price => None (which the firewall treats as BLOCK)."""

from __future__ import annotations

from apex_one.core.schemas.compute import Pricing


class CostEstimator:
    @staticmethod
    def estimate(pricing: Pricing, input_tokens: int = 2000, output_tokens: int = 2000) -> float | None:
        parts = (pricing.input_per_mtok_usd, pricing.output_per_mtok_usd, pricing.per_request_usd)
        if any(p is None for p in parts):
            return None
        assert pricing.input_per_mtok_usd is not None and pricing.output_per_mtok_usd is not None
        assert pricing.per_request_usd is not None
        return (pricing.input_per_mtok_usd * input_tokens / 1e6
                + pricing.output_per_mtok_usd * output_tokens / 1e6
                + pricing.per_request_usd)
