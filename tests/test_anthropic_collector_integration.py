"""Integration: the Anthropic collector stores hourly buckets idempotently.

The full pipeline runs against a mock HTTP transport serving a real simulator
payload: fetch_usage -> normalize -> upsert. Running the backfill twice must
produce identical row counts (the idempotency guarantee).
"""

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from monitor.collectors.anthropic import AnthropicUsageSource
from monitor.config import settings
from monitor.db.upsert import upsert_usage_rows
from monitor.simulator.app import create_app


def _simulator_response(window_start: str, window_end: str) -> httpx.Response:
    """Get a real payload from the simulator to serve via the mock transport."""
    client = TestClient(create_app())
    resp = client.get(
        "/anthropic/v1/organizations/usage_report/messages",
        params={
            "starting_at": window_start,
            "ending_at": window_end,
            "bucket_width": "1h",
        },
        headers={"x-api-key": "test-key", "anthropic-version": "2023-06-01"},
    )
    return httpx.Response(
        status_code=200,
        json=resp.json(),
        request=httpx.Request(
            "GET",
            f"http://testserver/anthropic/v1/organizations/usage_report/messages?starting_at={window_start}&ending_at={window_end}&bucket_width=1h",
        ),
    )


def _mock_transport(window_start: str, window_end: str) -> httpx.MockTransport:
    response = _simulator_response(window_start, window_end)
    return httpx.MockTransport(lambda request: response)


@pytest.fixture()
def db():
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE usage_fact, collector_run, raw_payload"))
    yield engine
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE usage_fact, collector_run, raw_payload"))
    engine.dispose()


class TestAnthropicCollectorIdempotency:
    def test_backfill_twice_produces_identical_row_counts(self, db) -> None:
        window = ("2026-10-14T10:00:00Z", "2026-10-14T12:00:00Z")

        # First backfill
        source1 = AnthropicUsageSource(
            base_url="http://testserver/anthropic",
            admin_key="test-key",
            transport=_mock_transport(*window),
        )
        rows1, _ = source1.fetch_usage(window, bucket_width="1h")
        with db.begin() as conn:
            upsert_usage_rows(conn, rows1)
            count1 = conn.execute(text("SELECT count(*) FROM usage_fact")).scalar_one()

        # Second backfill, same window
        source2 = AnthropicUsageSource(
            base_url="http://testserver/anthropic",
            admin_key="test-key",
            transport=_mock_transport(*window),
        )
        rows2, _ = source2.fetch_usage(window, bucket_width="1h")
        with db.begin() as conn:
            upsert_usage_rows(conn, rows2)
            count2 = conn.execute(text("SELECT count(*) FROM usage_fact")).scalar_one()

        assert count1 == count2
        assert count1 > 0

    def test_collector_records_run_and_raw_payload(self, db) -> None:
        from monitor.db.upsert import run_collection

        window = ("2026-10-14T10:00:00Z", "2026-10-14T11:00:00Z")
        source = AnthropicUsageSource(
            base_url="http://testserver/anthropic",
            admin_key="test-key",
            transport=_mock_transport(*window),
        )

        with db.begin() as conn:
            rows_written = run_collection(conn, source, window, bucket_width="1h")

            run = conn.execute(
                text(
                    "SELECT source, rows_written, success"
                    " FROM collector_run ORDER BY id DESC LIMIT 1"
                )
            ).fetchone()
            assert run.source == "anthropic.usage"
            assert run.rows_written == rows_written
            assert run.success is True

            payload_count = conn.execute(text("SELECT count(*) FROM raw_payload")).scalar_one()
            assert payload_count == 1
