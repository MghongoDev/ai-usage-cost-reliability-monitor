"""Cost normalization: provider payloads to cost_fact rows."""

from monitor.collectors.normalize_cost import (
    normalize_anthropic_costs,
    normalize_openai_costs,
)


class TestAnthropicCostNormalization:
    def test_converts_cents_to_dollars(self) -> None:
        payload = {
            "data": [
                {
                    "starting_at": "2026-10-14T00:00:00Z",
                    "ending_at": "2026-10-15T00:00:00Z",
                    "results": [
                        {
                            "amount": "123.78",  # cents
                            "currency": "USD",
                            "description": "Claude Opus 5.5 Usage - Input Tokens",
                            "model": "claude-opus-5-5",
                            "cost_type": "tokens",
                            "workspace_id": "wrkspc_01",
                        }
                    ],
                }
            ]
        }
        rows = normalize_anthropic_costs(payload)
        assert len(rows) == 1
        row = rows[0]
        assert row["provider"] == "anthropic"
        assert row["day"] == "2026-10-14"
        assert row["line_item"] == "Claude Opus 5.5 Usage - Input Tokens"
        assert row["amount_usd"] == 1.2378  # dollars
        assert row["scope_id"] == "wrkspc_01"


class TestOpenAICostNormalization:
    def test_amount_value_is_dollars(self) -> None:
        payload = {
            "object": "page",
            "data": [
                {
                    "start_time": 1729000000,
                    "end_time": 17290086400,
                    "results": [
                        {
                            "amount": {"value": "1.25", "currency": "USD"},
                            "line_item": "GPT-4o Usage",
                            "project_id": "proj_01",
                        }
                    ],
                }
            ],
        }
        rows = normalize_openai_costs(payload)
        assert len(rows) == 1
        row = rows[0]
        assert row["provider"] == "openai"
        assert row["line_item"] == "GPT-4o Usage"
        assert row["amount_usd"] == 1.25
        assert row["scope_id"] == "proj_01"
