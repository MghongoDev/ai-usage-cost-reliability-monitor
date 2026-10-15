"""Integration: cost collection stores daily cost_fact rows.

The full pipeline runs against a mock HTTP transport serving real simulator
payloads: fetch_costs -> normalize -> upsert. Also verifies the estimated
cost query flags unpriced models.
"""

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from monitor.collectors.anthropic import AnthropicUsageSource
from monitor.collectors.openai import OpenAIUsageSource
from monitor.config import settings
from monitor.db.upsert import estimated_cost_query, upsert_cost_rows
from monitor.simulator.app import create_app


def _anthropic_cost_response() -> httpx.Response:
    client = TestClient(create_app())
    resp = client.get(
        "/anthropic/v1/organizations/cost_report",
        params={
            "starting_at": "2026-10-14T00:00:00Z",
            "ending_at": "2026-10-15T00:00:00Z",
            "bucket_width": "1d",
            "group_by": ["description"],
        },
        headers={"x-api-key": "test-key", "anthropic-version": "2023-06-01"},
    )
    return httpx.Response(
        status_code=200,
        json=resp.json(),
        request=httpx.Request(
            "GET",
            "http://testserver/anthropic/v1/organizations/cost_report",
        ),
    )


def _openai_cost_response() -> httpx.Response:
    client = TestClient(create_app())
    resp = client.get(
        "/openai/v1/organization/costs",
        params={
            "start_time": 1729000000,
            "end_time": 17290086400,
            "bucket_width": "1d",
            "group_by": ["project_id", "line_item"],
        },
        headers={"Authorization": "Bearer test-key"},
    )
    return httpx.Response(
        status_code=200,
        json=resp.json(),
        request=httpx.Request(
            "GET",
            "http://testserver/openai/v1/organization/costs",
        ),
    )


@pytest.fixture()
def db():
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE cost_fact, usage_fact, price_table"))
    yield engine
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE cost_fact, usage_fact, price_table"))
    engine.dispose()


class TestCostCollection:
    def test_anthropic_costs_stored(self, db) -> None:
        source = AnthropicUsageSource(
            base_url="http://testserver/anthropic",
            admin_key="test-key",
            transport=httpx.MockTransport(lambda r: _anthropic_cost_response()),
        )
        rows = source.fetch_costs(("2026-10-14T00:00:00Z", "2026-10-15T00:00:00Z"))
        with db.begin() as conn:
            upsert_cost_rows(conn, rows)
            count = conn.execute(text("SELECT count(*) FROM cost_fact")).scalar_one()
        assert count > 0

    def test_openai_costs_stored(self, db) -> None:
        source = OpenAIUsageSource(
            base_url="http://testserver/openai",
            admin_key="test-key",
            transport=httpx.MockTransport(lambda r: _openai_cost_response()),
        )
        rows = source.fetch_costs((1729000000, 17290086400))
        with db.begin() as conn:
            upsert_cost_rows(conn, rows)
            count = conn.execute(text("SELECT count(*) FROM cost_fact")).scalar_one()
        assert count > 0

    def test_estimated_cost_query_flags_unpriced(self, db) -> None:
        from monitor.collectors.cost import seed_price_table
        from monitor.db.upsert import upsert_usage_rows

        # Seed prices
        with db.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO price_table (provider, model, token_class, usd_per_million,"
                    " effective_from) VALUES (:provider, :model, :token_class, :usd_per_million,"
                    " :effective_from)"
                ),
                seed_price_table(),
            )

        # Insert usage: one priced model, one unpriced
        with db.begin() as conn:
            upsert_usage_rows(
                conn,
                [
                    {
                        "provider": "anthropic",
                        "bucket_start": "2026-10-14T10:00:00Z",
                        "bucket_width": "1h",
                        "scope_id": "wrkspc_01",
                        "api_key_id": "apikey_01",
                        "model": "claude-opus-5-5",
                        "requests": 5,
                        "input_uncached": 1000,
                        "input_cached": 0,
                        "cache_creation": 0,
                        "output_tokens": 500,
                        "extra": "{}",
                    },
                    {
                        "provider": "anthropic",
                        "bucket_start": "2026-10-14T10:00:00Z",
                        "bucket_width": "1h",
                        "scope_id": "wrkspc_01",
                        "api_key_id": "apikey_02",
                        "model": "unknown-model",
                        "requests": 5,
                        "input_uncached": 1000,
                        "input_cached": 0,
                        "cache_creation": 0,
                        "output_tokens": 500,
                        "extra": "{}",
                    },
                ],
            )
            rows = estimated_cost_query(conn)

        # Find the priced and unpriced rows
        priced = [r for r in rows if r.model == "claude-opus-5-5"]
        unpriced = [r for r in rows if r.model == "unknown-model"]
        assert len(priced) == 1
        assert priced[0].estimated_cost_usd is not None
        assert priced[0].unpriced is False
        assert len(unpriced) == 1
        assert unpriced[0].estimated_cost_usd is None
        assert unpriced[0].unpriced is True
