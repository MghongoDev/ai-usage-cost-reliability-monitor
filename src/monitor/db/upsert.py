"""Idempotent upserts and the collect runner.

Every run re-pulls the trailing window and upserts, so re-running produces
identical row counts. Each run is recorded in collector_run (source, window,
rows, success, error) and every raw payload is stored in raw_payload with a
retention policy.
"""

from typing import Any

from sqlalchemy import Connection, text

from monitor.collectors.base import UsageSource


def upsert_usage_rows(conn: Connection, rows: list[dict[str, Any]]) -> int:
    """Upsert usage_fact rows. Returns the number of rows written."""
    if not rows:
        return 0
    import json

    # Serialize the extra jsonb field; psycopg can't adapt a dict directly.
    rows = [{**row, "extra": json.dumps(row.get("extra", {}))} for row in rows]
    stmt = text(
        """
        INSERT INTO usage_fact (
            provider, bucket_start, bucket_width, scope_id, api_key_id, model,
            requests, input_uncached, input_cached, cache_creation, output_tokens, extra
        ) VALUES (
            :provider, :bucket_start, :bucket_width, :scope_id, :api_key_id, :model,
            :requests, :input_uncached, :input_cached, :cache_creation, :output_tokens,
            CAST(:extra AS jsonb)
        )
        ON CONFLICT (provider, bucket_start, bucket_width, dims_key)
        DO UPDATE SET
            requests = EXCLUDED.requests,
            input_uncached = EXCLUDED.input_uncached,
            input_cached = EXCLUDED.input_cached,
            cache_creation = EXCLUDED.cache_creation,
            output_tokens = EXCLUDED.output_tokens,
            extra = EXCLUDED.extra,
            fetched_at = now()
        """
    )
    conn.execute(stmt, rows)
    return len(rows)


def record_raw_payload(
    conn: Connection, provider: str, endpoint: str, params: dict[str, Any], body: dict[str, Any]
) -> None:
    """Store a raw payload for schema-drift investigation."""
    import json

    conn.execute(
        text(
            """
            INSERT INTO raw_payload (provider, endpoint, params, body)
            VALUES (:provider, :endpoint, :params, :body)
            """
        ),
        {
            "provider": provider,
            "endpoint": endpoint,
            "params": json.dumps(params),
            "body": json.dumps(body),
        },
    )


def record_collector_run(
    conn: Connection,
    source: str,
    window_start: str,
    window_end: str,
    rows_written: int,
    success: bool,
    error: str | None = None,
) -> None:
    """Record a collector run."""
    conn.execute(
        text(
            """
            INSERT INTO collector_run (
                source, window_start, window_end, rows_written, success, error, finished_at
            )
            VALUES (:source, :window_start, :window_end, :rows_written, :success, :error, now())
            """
        ),
        {
            "source": source,
            "window_start": window_start,
            "window_end": window_end,
            "rows_written": rows_written,
            "success": success,
            "error": error,
        },
    )


def run_collection(
    conn: Connection,
    source: UsageSource,
    window: tuple[str, str],
    bucket_width: str = "1h",
) -> int:
    """Fetch usage, upsert, and record the run. Returns rows written.

    This is the thin runner that ties fetch + upsert + record together so
    every collect cycle lands in collector_run and raw_payload.
    """
    start, end = window
    try:
        rows, _ = source.fetch_usage(window, bucket_width=bucket_width)
        upsert_usage_rows(conn, rows)
        if hasattr(source, "last_raw_response") and source.last_raw_response is not None:
            record_raw_payload(
                conn,
                provider="anthropic",
                endpoint="/v1/organizations/usage_report/messages",
                params={"starting_at": start, "ending_at": end, "bucket_width": bucket_width},
                body=source.last_raw_response,
            )
        record_collector_run(
            conn,
            source="anthropic.usage",
            window_start=start,
            window_end=end,
            rows_written=len(rows),
            success=True,
        )
        return len(rows)
    except Exception as exc:
        record_collector_run(
            conn,
            source="anthropic.usage",
            window_start=start,
            window_end=end,
            rows_written=0,
            success=False,
            error=str(exc),
        )
        raise
