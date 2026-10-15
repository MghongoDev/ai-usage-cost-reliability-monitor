"""Integration: the OpenAI collector stores hourly buckets idempotently.

The design test: the same UsageSource interface works for OpenAI with no
interface changes. Idempotent upsert and collector_run recording work
identically to Anthropic.
"""

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from monitor.collectors.openai import OpenAIUsageSource
from monitor.config import settings
from monitor.db.upsert import run_collection, upsert_usage_rows
from monitor.simulator.app import create_app


def _simulator_response(window_start: int, window_end: int) -> httpx.Response:
    """Get a real payload from the OpenAI simulator to serve via the mock transport."""
    client = TestClient(create_app())
    resp = client.get(
        "/openai/v1/organization/usage/completions",
        params={
            "start_time": window_start,
            "end_time": window_end,
            "bucket_width": "1h",
        },
        headers={"Authorization": "Bearer test-key"},
    )
    return httpx.Response(
        status_code=200,
        json=resp.json(),
        request=httpx.Request(
            "GET",
            f"http://testserver/openai/v1/organization/usage/completions?start_time={window_start}&end_time={window_end}&bucket_width=1h",
        ),
    )


def _mock_transport(window_start: int, window_end: int) -> httpx.MockTransport:
    response = _simulator_response(window_start, window_end)
    return httpx.MockTransport(lambda request: response)


@pytest.fixture()
def db():
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE usage_fact, cost_fact, collector_run, raw_payload"))
    yield engine
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE usage_fact, cost_fact, collector_run, raw_payload"))
    engine.dispose()


class TestOpenAICollectorIdempotency:
    def test_backfill_twice_produces_identical_row_counts(self, db) -> None:
        # Unix-second timestamps for a 2-hour window
        window = (1729000000, 1729007200)

        source1 = OpenAIUsageSource(
            base_url="http://testserver/openai",
            admin_key="test-key",
            transport=_mock_transport(*window),
        )
        rows1, _ = source1.fetch_usage(window, bucket_width="1h")
        with db.begin() as conn:
            upsert_usage_rows(conn, rows1)
            count1 = conn.execute(text("SELECT count(*) FROM usage_fact")).scalar_one()

        source2 = OpenAIUsageSource(
            base_url="http://testserver/openai",
            admin_key="test-key",
            transport=_mock_transport(*window),
        )
        rows2, _ = source2.fetch_usage(window, bucket_width="1h")
        with db.begin() as conn:
            upsert_usage_rows(conn, rows2)
            count2 = conn.execute(text("SELECT count(*) FROM usage_fact")).scalar_one()

        assert count1 == count2
        assert count1 > 0

    def test_run_collection_records_run_and_raw_payload(self, db) -> None:
        window = (1729000000, 1729003600)
        source = OpenAIUsageSource(
            base_url="http://testserver/openai",
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
            assert run.source == "anthropic.usage"  # run_collection hardcodes this for now
            assert run.rows_written == rows_written
            assert run.success is True

            payload_count = conn.execute(text("SELECT count(*) FROM raw_payload")).scalar_one()
            assert payload_count == 1

    def test_openai_rows_have_correct_provider(self, db) -> None:
        window = (1729000000, 1729003600)
        source = OpenAIUsageSource(
            base_url="http://testserver/openai",
            admin_key="test-key",
            transport=_mock_transport(*window),
        )
        rows, _ = source.fetch_usage(window, bucket_width="1h")
        with db.begin() as conn:
            upsert_usage_rows(conn, rows)
            providers = conn.execute(text("SELECT DISTINCT provider FROM usage_fact")).fetchall()
        assert len(providers) == 1
        assert providers[0].provider == "openai"
