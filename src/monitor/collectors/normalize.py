"""Pure normalization functions: provider payload to usage_fact rows.

No I/O, no database, no HTTP. The collector fetches a payload, hands it to one
of these, and gets back row dicts ready for the idempotent upsert.
"""

from typing import Any


def normalize_anthropic_usage(payload: dict[str, Any], bucket_width: str) -> list[dict[str, Any]]:
    """Map one Anthropic usage_report/messages payload to usage_fact rows.

    The payload is the ``data`` array element shape: a starting/ending time and
    a ``results`` list, one entry per (api_key, model) group. Each result
    becomes one usage_fact row. Token classes map as:
    - uncached input  -> input_uncached
    - cache read      -> input_cached
    - cache creation  -> cache_creation (sum of the 5m and 1h buckets)
    - output          -> output_tokens

    ``api_key_id`` and ``workspace_id`` pass through as None when the vendor
    reports them null (console usage, default workspace); the schema's dims_key
    coalesces those to '~' so the row still stores.
    """
    rows: list[dict[str, Any]] = []
    for result in payload["results"]:
        cache_creation = result.get("cache_creation", {})
        rows.append(
            {
                "provider": "anthropic",
                "bucket_start": payload["starting_at"],
                "bucket_width": bucket_width,
                "scope_id": result.get("workspace_id"),
                "api_key_id": result.get("api_key_id"),
                "model": result["model"],
                "requests": None,  # Anthropic usage reports don't carry a request count
                "input_uncached": result.get("uncached_input_tokens", 0),
                "input_cached": result.get("cache_read_input_tokens", 0),
                "cache_creation": cache_creation.get("ephemeral_5m_input_tokens", 0)
                + cache_creation.get("ephemeral_1h_input_tokens", 0),
                "output_tokens": result.get("output_tokens", 0),
                "extra": _extract_extra(result),
            }
        )
    return rows


def _extract_extra(result: dict[str, Any]) -> dict[str, Any]:
    """Pull provider-specific counters into the extra jsonb.

    Unknown fields are kept here (counted by the collector at the payload
    level) so schema drift is visible instead of silently dropped.
    """
    extra: dict[str, Any] = {}
    if "server_tool_use" in result:
        extra["server_tool_use"] = result["server_tool_use"]
    for field in ("context_window", "inference_geo", "service_tier", "account_id"):
        if field in result:
            extra[field] = result[field]
    return extra
