"""Pure normalization: provider cost payloads to cost_fact rows."""

from datetime import UTC, datetime
from typing import Any


def normalize_anthropic_costs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Map an Anthropic cost_report payload to cost_fact rows.

    Anthropic: daily buckets, amount as decimal string in lowest units (cents),
    grouped by description/workspace_id. The amount is converted to dollars.
    """
    rows: list[dict[str, Any]] = []
    for bucket in payload.get("data", []):
        for result in bucket.get("results", []):
            # Amount is a decimal string in cents (lowest units)
            amount_cents = float(result.get("amount", "0"))
            rows.append(
                {
                    "provider": "anthropic",
                    "day": bucket["starting_at"][:10],  # "2026-10-14T00:00:00Z" -> "2026-10-14"
                    "scope_id": result.get("workspace_id"),
                    "line_item": result.get("description", "Unknown"),
                    "amount_usd": amount_cents / 100.0,
                    "description": result.get("description"),
                    "cost_type": result.get("cost_type"),
                }
            )
    return rows


def normalize_openai_costs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Map an OpenAI costs payload to cost_fact rows.

    OpenAI: daily buckets, amount as {value, currency}, grouped by
    project_id/line_item. The value is already in dollars.
    """
    rows: list[dict[str, Any]] = []
    for bucket in payload.get("data", []):
        for result in bucket.get("results", []):
            amount_obj = result.get("amount", {})
            rows.append(
                {
                    "provider": "openai",
                    "day": datetime.fromtimestamp(bucket["start_time"], tz=UTC).strftime(
                        "%Y-%m-%d"
                    ),
                    "scope_id": result.get("project_id"),
                    "line_item": result.get("line_item", "Unknown"),
                    "amount_usd": float(amount_obj.get("value", "0")),
                    "description": result.get("line_item"),
                    "cost_type": None,
                }
            )
    return rows
