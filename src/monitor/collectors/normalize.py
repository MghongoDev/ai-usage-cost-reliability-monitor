"""Pure normalization functions: provider payload to usage_fact rows.

No I/O, no database, no HTTP. The collector fetches a payload, validates it
through Pydantic models (unknown fields counted, missing required fields
fail loudly), and hands the rows to the idempotent upsert.
"""

from typing import Any

from monitor.collectors.models import UsageReport, count_nested_unknown


def normalize_anthropic_usage(
    payload: dict[str, Any], bucket_width: str
) -> tuple[list[dict[str, Any]], int]:
    """Map one Anthropic usage_report/messages payload to usage_fact rows.

    Returns (rows, unknown_field_count). Rows are ready for the idempotent
    upsert. The unknown field count is logged by the collector so schema
    drift is visible.

    Token classes map as:
    - uncached input  -> input_uncached
    - cache read      -> input_cached
    - cache creation  -> cache_creation (sum of the 5m and 1h buckets)
    - output          -> output_tokens

    ``api_key_id`` and ``workspace_id`` pass through as None when the vendor
    reports them null (console usage, default workspace); the schema's dims_key
    coalesces those to '~' so the row still stores.
    """
    report = UsageReport.model_validate(payload)
    unknown = count_nested_unknown(report)

    rows: list[dict[str, Any]] = []
    for bucket in report.data:
        for result in bucket.results:
            rows.append(
                {
                    "provider": "anthropic",
                    "bucket_start": bucket.starting_at,
                    "bucket_width": bucket_width,
                    "scope_id": result.workspace_id,
                    "api_key_id": result.api_key_id,
                    "model": result.model,
                    "requests": None,  # Anthropic usage reports don't carry a request count
                    "input_uncached": result.uncached_input_tokens,
                    "input_cached": result.cache_read_input_tokens,
                    "cache_creation": result.cache_creation.ephemeral_5m_input_tokens
                    + result.cache_creation.ephemeral_1h_input_tokens,
                    "output_tokens": result.output_tokens,
                    "extra": _extract_extra(result),
                }
            )
    return rows, unknown


def _extract_extra(result: Any) -> dict[str, Any]:
    """Pull provider-specific counters into the extra jsonb."""
    extra: dict[str, Any] = {}
    if result.server_tool_use:
        extra["server_tool_use"] = result.server_tool_use
    # Capture any extra fields Pydantic allowed through
    if result.model_extra:
        for key, value in result.model_extra.items():
            extra[key] = value
    return extra
