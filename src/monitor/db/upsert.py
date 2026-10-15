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


def upsert_cost_rows(conn: Connection, rows: list[dict[str, Any]]) -> int:
    """Upsert cost_fact rows. Returns the number of rows written."""
    if not rows:
        return 0
    stmt = text(
        """
        INSERT INTO cost_fact (
            provider, day, scope_id, line_item, amount_usd, description, cost_type
        )
        VALUES (:provider, :day, :scope_id, :line_item, :amount_usd, :description, :cost_type)
        ON CONFLICT (provider, day, scope_key, line_item)
        DO UPDATE SET
            amount_usd = EXCLUDED.amount_usd,
            description = EXCLUDED.description,
            cost_type = EXCLUDED.cost_type,
            fetched_at = now()
        """
    )
    conn.execute(stmt, rows)
    return len(rows)


def estimated_cost_query(conn: Connection) -> Any:
    """Estimated cost per hour/key/model from usage times price.

    Models with no price row show cost as NULL (unpriced), never zero.
    """
    stmt = text(
        """
        SELECT
            u.provider,
            u.bucket_start,
            u.api_key_id,
            u.model,
            u.input_uncached,
            u.input_cached,
            u.cache_creation,
            u.output_tokens,
            CASE
                WHEN p.input_uncached IS NULL OR p.input_cached IS NULL
                     OR p.cache_creation IS NULL OR p.output IS NULL
                THEN NULL
                ELSE (
                    u.input_uncached * p.input_uncached / 1000000.0
                    + u.input_cached * p.input_cached / 1000000.0
                    + u.cache_creation * p.cache_creation / 1000000.0
                    + u.output_tokens * p.output / 1000000.0
                )
            END AS estimated_cost_usd,
            CASE
                WHEN p.input_uncached IS NULL OR p.input_cached IS NULL
                     OR p.cache_creation IS NULL OR p.output IS NULL
                THEN TRUE
                ELSE FALSE
            END AS unpriced
        FROM usage_fact u
        LEFT JOIN (
            SELECT provider, model,
                MAX(CASE WHEN token_class = 'input_uncached'
                    THEN usd_per_million END) AS input_uncached,
                MAX(CASE WHEN token_class = 'input_cached'
                    THEN usd_per_million END) AS input_cached,
                MAX(CASE WHEN token_class = 'cache_creation'
                    THEN usd_per_million END) AS cache_creation,
                MAX(CASE WHEN token_class = 'output'
                    THEN usd_per_million END) AS output
            FROM price_table
            WHERE effective_from <= CURRENT_DATE
              AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
            GROUP BY provider, model
        ) p ON p.model = u.model AND p.provider = u.provider
        ORDER BY u.bucket_start DESC, u.provider, u.api_key_id
        """
    )
    return conn.execute(stmt).fetchall()


def reconciliation_query(conn: Connection) -> Any:
    """Estimated vs billed cost per scope per day, with recon_error_pct."""
    stmt = text(
        """
        SELECT
            e.provider,
            e.scope_id,
            e.day,
            e.estimated_usd,
            b.billed_usd,
            CASE
                WHEN b.billed_usd IS NULL OR b.billed_usd = 0 THEN NULL
                ELSE ABS(e.estimated_usd - b.billed_usd) / b.billed_usd * 100
            END AS recon_error_pct
        FROM (
            SELECT u.provider, u.scope_id, u.bucket_start::date AS day,
                SUM(
                    u.input_uncached * p.input_uncached / 1000000.0
                    + u.input_cached * p.input_cached / 1000000.0
                    + u.cache_creation * p.cache_creation / 1000000.0
                    + u.output_tokens * p.output / 1000000.0
                ) AS estimated_usd
            FROM usage_fact u
            LEFT JOIN (
                SELECT provider, model,
                    MAX(CASE WHEN token_class = 'input_uncached'
                        THEN usd_per_million END) AS input_uncached,
                    MAX(CASE WHEN token_class = 'input_cached'
                        THEN usd_per_million END) AS input_cached,
                    MAX(CASE WHEN token_class = 'cache_creation'
                        THEN usd_per_million END) AS cache_creation,
                    MAX(CASE WHEN token_class = 'output'
                        THEN usd_per_million END) AS output
                FROM price_table
                WHERE effective_from <= CURRENT_DATE
                  AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
                GROUP BY provider, model
            ) p ON p.model = u.model AND p.provider = u.provider
            WHERE p.input_uncached IS NOT NULL
            GROUP BY u.provider, u.scope_id, u.bucket_start::date
        ) e
        FULL OUTER JOIN (
            SELECT provider, scope_id, day, SUM(amount_usd) AS billed_usd
            FROM cost_fact
            GROUP BY provider, scope_id, day
        ) b ON b.provider = e.provider AND b.scope_id = e.scope_id AND b.day = e.day
        ORDER BY e.day, e.provider, e.scope_id
        """
    )
    return conn.execute(stmt).fetchall()


def budget_projection_query(conn: Connection, month: str) -> Any:
    """Month-to-date, projected month-end, and percent of budget per scope."""
    stmt = text(
        """
        SELECT
            b.scope_id,
            b.month,
            b.amount_usd AS budget_usd,
            COALESCE(SUM(c.amount_usd), 0) AS mtd_usd,
            CASE
                WHEN EXTRACT(DAY FROM CURRENT_DATE) = 0 THEN 0
                ELSE COALESCE(SUM(c.amount_usd), 0) / EXTRACT(DAY FROM CURRENT_DATE)
                     * EXTRACT(DAY FROM (
                         DATE_TRUNC('month', b.month::date)
                         + INTERVAL '1 month' - INTERVAL '1 day'
                     ))
            END AS projected_usd,
            CASE
                WHEN b.amount_usd = 0 THEN NULL
                ELSE COALESCE(SUM(c.amount_usd), 0) / b.amount_usd * 100
            END AS pct_of_budget
        FROM budget b
        LEFT JOIN cost_fact c ON c.scope_id = b.scope_id
            AND c.day >= DATE_TRUNC('month', b.month::date)
            AND c.day < DATE_TRUNC('month', b.month::date) + INTERVAL '1 month'
        WHERE b.month = :month
        GROUP BY b.scope_id, b.month, b.amount_usd
        ORDER BY b.scope_id
        """
    )
    return conn.execute(stmt, {"month": month}).fetchall()


def upsert_budget_rows(conn: Connection, rows: list[dict[str, Any]]) -> int:
    """Upsert budget rows. Returns the number of rows written."""
    if not rows:
        return 0
    stmt = text(
        """
        INSERT INTO budget (scope_id, month, amount_usd)
        VALUES (:scope_id, :month, :amount_usd)
        ON CONFLICT (scope_id, month)
        DO UPDATE SET amount_usd = EXCLUDED.amount_usd
        """
    )
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
