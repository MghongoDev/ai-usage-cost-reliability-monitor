"""Idempotent upserts and the collect runner.

Every run re-pulls the trailing window and upserts, so re-running produces
identical row counts. Each run is recorded in collector_run (source, window,
rows, success, error) and every raw payload is stored in raw_payload with a
retention policy.
"""

from typing import Any

from sqlalchemy import Connection, text


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
