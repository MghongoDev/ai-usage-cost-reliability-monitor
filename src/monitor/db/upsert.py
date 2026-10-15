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
    window_start: str | int,
    window_end: str | int,
    rows_written: int,
    success: bool,
    error: str | None = None,
) -> None:
    """Record a collector run. Accepts ISO strings or Unix-second integers."""
    from datetime import UTC, datetime

    def _to_ts(val: str | int) -> str:
        if isinstance(val, int):
            return datetime.fromtimestamp(val, tz=UTC).isoformat()
        return val

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
            "window_start": _to_ts(window_start),
            "window_end": _to_ts(window_end),
            "rows_written": rows_written,
            "success": success,
            "error": error,
        },
    )


def upsert_key_inventory_rows(conn: Connection, rows: list[dict[str, Any]]) -> int:
    """Upsert key_inventory rows. Returns the number of rows written."""
    if not rows:
        return 0
    import json

    stmt = text(
        """
        INSERT INTO key_inventory (
            provider, snapshot_date, api_key_id, scope_id, name, status,
            owner, created_at, last_used_at, extra
        ) VALUES (
            :provider, CURRENT_DATE, :api_key_id, :scope_id, :name, :status,
            :owner, :created_at, :last_used_at, CAST(:extra AS jsonb)
        )
        ON CONFLICT (provider, snapshot_date, api_key_id)
        DO UPDATE SET
            scope_id = EXCLUDED.scope_id,
            name = EXCLUDED.name,
            status = EXCLUDED.status,
            owner = EXCLUDED.owner,
            created_at = EXCLUDED.created_at,
            last_used_at = EXCLUDED.last_used_at,
            extra = EXCLUDED.extra,
            fetched_at = now()
        """
    )
    rows = [{**r, "extra": json.dumps(r.get("extra", {}))} for r in rows]
    conn.execute(stmt, rows)
    return len(rows)


def unused_keys_query(conn: Connection, days: int = 30) -> Any:
    """Find keys with no usage for the last N days."""
    stmt = text(
        """
        SELECT k.api_key_id, k.provider, k.name, k.owner, k.status
        FROM key_inventory k
        WHERE NOT EXISTS (
            SELECT 1 FROM usage_fact u
            WHERE u.api_key_id = k.api_key_id
              AND u.provider = k.provider
              AND u.bucket_start >= now() - make_interval(days => :days)
        )
        ORDER BY k.provider, k.api_key_id
        """
    )
    return conn.execute(stmt, {"days": days}).fetchall()


def run_collection(
    conn: Connection,
    source: UsageSource,
    window: tuple[str | int, str | int],
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
