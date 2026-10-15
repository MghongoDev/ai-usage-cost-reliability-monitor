"""Pure normalization: OpenAI usage payload to usage_fact rows.

OpenAI's shape differs from Anthropic: Unix-second timestamps, a page
envelope with next_page cursor, and input_cache_write_tokens as a separate
field (not nested).
"""

from datetime import UTC, datetime
from typing import Any

from monitor.collectors.models import OpenAIUsageReport, count_nested_unknown


def _unix_to_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def normalize_openai_usage(
    payload: dict[str, Any], bucket_width: str
) -> tuple[list[dict[str, Any]], int]:
    """Map one OpenAI usage/completions payload to usage_fact rows.

    Returns (rows, unknown_field_count). Token classes map as:
    - input_uncached_tokens  -> input_uncached
    - input_cached_tokens    -> input_cached
    - input_cache_write_tokens -> cache_creation
    - output_tokens          -> output_tokens
    - num_model_requests     -> requests
    """
    report = OpenAIUsageReport.model_validate(payload)
    unknown = count_nested_unknown(report)

    rows: list[dict[str, Any]] = []
    for bucket in report.data:
        for result in bucket.results:
            rows.append(
                {
                    "provider": "openai",
                    "bucket_start": _unix_to_iso(bucket.start_time),
                    "bucket_width": bucket_width,
                    "scope_id": result.project_id,
                    "api_key_id": result.api_key_id,
                    "model": result.model,
                    "requests": result.num_model_requests,
                    "input_uncached": result.input_uncached_tokens,
                    "input_cached": result.input_cached_tokens,
                    "cache_creation": result.input_cache_write_tokens,
                    "output_tokens": result.output_tokens,
                    "extra": _extract_extra(result),
                }
            )
    return rows, unknown


def _extract_extra(result: Any) -> dict[str, Any]:
    """Pull provider-specific fields into the extra jsonb."""
    extra: dict[str, Any] = {}
    if result.model_extra:
        for key, value in result.model_extra.items():
            extra[key] = value
    return extra
