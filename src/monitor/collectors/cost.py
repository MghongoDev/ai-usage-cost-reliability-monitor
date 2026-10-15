"""Cost estimation: usage times price, with unpriced models visible.

Prices are data (in the price_table), not code. The seed_price_table function
loads the researched pricing from docs/api-notes-anthropic.md and
docs/api-notes-openai.md. Estimated cost = usage_tokens * (usd_per_million /
1_000_000). A model with no price row returns None (unpriced), never 0.
"""

from typing import Any


def estimate_cost(usage: dict[str, Any], prices: dict[str, dict[str, float]]) -> float | None:
    """Estimate cost for one usage row. Returns None if any token class is unpriced.

    prices is {model: {token_class: usd_per_million}} using the price_table's
    token_class names (input_uncached, input_cached, cache_creation, output).
    """
    model = usage["model"]
    if model not in prices:
        return None
    model_prices = prices[model]
    total = 0.0
    for price_class, usage_field in (
        ("input_uncached", "input_uncached"),
        ("input_cached", "input_cached"),
        ("cache_creation", "cache_creation"),
        ("output", "output_tokens"),
    ):
        tokens = usage.get(usage_field, 0)
        if tokens == 0:
            continue
        if price_class not in model_prices:
            return None
        total += tokens * (model_prices[price_class] / 1_000_000)
    return total


def load_prices(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Index price rows by model then token_class."""
    prices: dict[str, dict[str, float]] = {}
    for row in rows:
        model = row["model"]
        token_class = row["token_class"]
        if model not in prices:
            prices[model] = {}
        prices[model][token_class] = row["usd_per_million"]
    return prices


def seed_price_table() -> list[dict[str, Any]]:
    """Seed price_table from researched pricing.

    Prices are USD per million tokens, split by token class. Effective dates
    are set to 2026-10-14 (the research date). In production these would be
    loaded from a versioned source with proper effective_from dates.
    """
    effective_from = "2026-10-14"

    # Anthropic pricing (from docs/api-notes-anthropic.md, researched 2026-10-14)
    anthropic_prices = {
        "claude-opus-5-5": {
            "input_uncached": 4.00,
            "input_cached": 0.20,
            "cache_creation": 5.00,
            "output": 20.00,
        },
        "claude-opus-5": {
            "input_uncached": 5.00,
            "input_cached": 0.50,
            "cache_creation": 6.25,
            "output": 25.00,
        },
        "claude-sonnet-5": {
            "input_uncached": 2.00,
            "input_cached": 0.20,
            "cache_creation": 2.50,
            "output": 10.00,
        },
        "claude-sonnet-4.6": {
            "input_uncached": 3.00,
            "input_cached": 0.30,
            "cache_creation": 3.75,
            "output": 15.00,
        },
        "claude-haiku-5-5": {
            "input_uncached": 0.10,
            "input_cached": 0.01,
            "cache_creation": 0.125,
            "output": 0.50,
        },
        "claude-haiku-4.5": {
            "input_uncached": 1.00,
            "input_cached": 0.10,
            "cache_creation": 1.25,
            "output": 5.00,
        },
    }

    # OpenAI pricing (from docs/api-notes-openai.md, researched 2026-10-14)
    openai_prices = {
        "gpt-4o": {
            "input_uncached": 2.50,
            "input_cached": 1.25,
            "cache_creation": 2.50,
            "output": 10.00,
        },
        "gpt-4o-mini": {
            "input_uncached": 0.15,
            "input_cached": 0.075,
            "cache_creation": 0.15,
            "output": 0.60,
        },
        "o3-mini": {
            "input_uncached": 1.10,
            "input_cached": 0.55,
            "cache_creation": 1.10,
            "output": 4.40,
        },
    }

    rows: list[dict[str, Any]] = []
    for provider, prices in (("anthropic", anthropic_prices), ("openai", openai_prices)):
        for model, classes in prices.items():
            for token_class, usd_per_million in classes.items():
                rows.append(
                    {
                        "provider": provider,
                        "model": model,
                        "token_class": token_class,
                        "usd_per_million": usd_per_million,
                        "effective_from": effective_from,
                    }
                )
    return rows
