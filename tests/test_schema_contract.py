"""Schema contract tests: the migration produces a database that behaves as specified.

These run against a real Postgres (DATABASE_URL). They test the database
behavior, not the Python that writes to it, so they survive refactors of the
collector and normalizer layers.
"""

import pytest
from sqlalchemy import create_engine, inspect, text

from monitor.config import settings

EXPECTED_TABLES = {
    "usage_fact",
    "cost_fact",
    "key_inventory",
    "price_table",
    "budget",
    "probe_result",
    "collector_run",
    "alert_event",
    "raw_payload",
}

UPSERT_NULL_DIMS = (
    "INSERT INTO usage_fact (provider, bucket_start, bucket_width,"
    " requests, input_uncached, output_tokens)"
    " VALUES ('anthropic', :bucket_start, '1h', :requests, 100, 50)"
    " ON CONFLICT (provider, bucket_start, bucket_width, dims_key)"
    " DO UPDATE SET requests = EXCLUDED.requests"
)


@pytest.fixture()
def db():
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE usage_fact"))
    yield engine
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE usage_fact"))
    engine.dispose()


class TestSchemaContract:
    def test_all_tables_exist(self, db) -> None:
        tables = set(inspect(db).get_table_names())
        assert tables >= EXPECTED_TABLES

    def test_usage_fact_primary_key_survives_null_dimensions(self, db) -> None:
        # A bucket with no scope, key, or model: all three dims null.
        # The first insert stores the row.
        with db.begin() as conn:
            conn.execute(
                text(UPSERT_NULL_DIMS), {"bucket_start": "2026-10-14T10:00:00Z", "requests": 5}
            )
        # The second insert, same dims key, updates instead of failing.
        with db.begin() as conn:
            conn.execute(
                text(UPSERT_NULL_DIMS), {"bucket_start": "2026-10-14T10:00:00Z", "requests": 9}
            )
            rows = conn.execute(
                text(
                    "SELECT requests, dims_key FROM usage_fact"
                    " WHERE provider='anthropic' AND bucket_start='2026-10-14T10:00:00Z'"
                )
            ).fetchall()
        assert len(rows) == 1
        assert rows[0].requests == 9
        assert rows[0].dims_key == "~|~|~"

    def test_cache_creation_column_exists(self, db) -> None:
        columns = {c["name"] for c in inspect(db).get_columns("usage_fact")}
        assert "cache_creation" in columns

    def test_identity_tables_use_identity_primary_keys(self, db) -> None:
        for table in ("probe_result", "collector_run", "raw_payload"):
            pk = inspect(db).get_pk_constraint(table)
            assert pk["constrained_columns"] == ["id"], f"{table} should have an id PK"
