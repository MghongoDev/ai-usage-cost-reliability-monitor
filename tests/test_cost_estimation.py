"""Cost estimation: usage times price, with unpriced models visible.

The core acceptance criterion: estimated cost derives from usage times the
versioned price table, and a model with no price row shows as unpriced,
never as silent zero.
"""

import pytest

from monitor.collectors.cost import (
    estimate_cost,
    load_prices,
    seed_price_table,
)


class TestEstimateCost:
    def test_known_cost_value(self) -> None:
        # Unit sanity: 1M tokens at $3.00/M = $3.00
        prices = {"claude-opus-5-5": {"input_uncached": 3.00, "output": 25.00}}
        usage = {
            "model": "claude-opus-5-5",
            "input_uncached": 1_000_000,
            "input_cached": 0,
            "cache_creation": 0,
            "output_tokens": 0,
        }
        cost = estimate_cost(usage, prices)
        assert cost == pytest.approx(3.00)

    def test_output_tokens_costed_separately(self) -> None:
        prices = {"claude-opus-5-5": {"input_uncached": 3.00, "output": 25.00}}
        usage = {
            "model": "claude-opus-5-5",
            "input_uncached": 0,
            "input_cached": 0,
            "cache_creation": 0,
            "output_tokens": 1_000_000,
        }
        cost = estimate_cost(usage, prices)
        assert cost == pytest.approx(25.00)

    def test_cached_input_uses_cached_price(self) -> None:
        prices = {
            "claude-opus-5-5": {
                "input_uncached": 3.00,
                "input_cached": 0.50,
                "cache_creation": 6.25,
                "output": 25.00,
            }
        }
        usage = {
            "model": "claude-opus-5-5",
            "input_uncached": 0,
            "input_cached": 1_000_000,
            "cache_creation": 1_000_000,
            "output_tokens": 0,
        }
        cost = estimate_cost(usage, prices)
        # 1M cached at $0.50/M + 1M cache creation at $6.25/M = $6.75
        assert cost == pytest.approx(6.75)

    def test_unpriced_model_returns_none(self) -> None:
        # A model with no price row must return None (unpriced), not 0.
        prices = {}
        usage = {
            "model": "unknown-model",
            "input_uncached": 1_000_000,
            "input_cached": 0,
            "cache_creation": 0,
            "output_tokens": 0,
        }
        cost = estimate_cost(usage, prices)
        assert cost is None

    def test_partial_pricing_returns_none(self) -> None:
        # If any token class is missing, the whole row is unpriced.
        prices = {"claude-opus-5-5": {"input_uncached": 3.00}}  # no output price
        usage = {
            "model": "claude-opus-5-5",
            "input_uncached": 0,
            "input_cached": 0,
            "cache_creation": 0,
            "output_tokens": 1_000_000,
        }
        cost = estimate_cost(usage, prices)
        assert cost is None


class TestSeedPriceTable:
    def test_seed_creates_rows_per_token_class(self) -> None:
        # Seed from researched pricing; verify separate rows per token class.
        rows = seed_price_table()
        assert len(rows) > 0
        # Each row has provider, model, token_class, usd_per_million, effective_from
        for row in rows:
            assert "provider" in row
            assert "model" in row
            assert "token_class" in row
            assert "usd_per_million" in row
            assert "effective_from" in row

    def test_anthropic_prices_present(self) -> None:
        rows = seed_price_table()
        anthropic = [r for r in rows if r["provider"] == "anthropic"]
        assert len(anthropic) > 0
        # Spot-check: Opus 5.5 input at $4.00/M
        opus_input = [
            r
            for r in anthropic
            if r["model"] == "claude-opus-5-5" and r["token_class"] == "input_uncached"
        ]
        assert len(opus_input) == 1
        assert opus_input[0]["usd_per_million"] == 4.00

    def test_openai_prices_present(self) -> None:
        rows = seed_price_table()
        openai = [r for r in rows if r["provider"] == "openai"]
        assert len(openai) > 0


class TestLoadPrices:
    def test_load_prices_indexes_by_model_and_class(self) -> None:
        rows = seed_price_table()
        prices = load_prices(rows)
        # prices[model][token_class] = usd_per_million
        assert "claude-opus-5-5" in prices
        assert "input_uncached" in prices["claude-opus-5-5"]
        assert prices["claude-opus-5-5"]["input_uncached"] == 4.00
