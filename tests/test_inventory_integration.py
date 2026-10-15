"""Integration: inventory collection stores daily snapshots idempotently.

The full pipeline runs against a mock HTTP transport serving real simulator
payloads: list_keys -> normalize -> upsert. Running the snapshot twice must
produce identical row counts (idempotent per day).
"""

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from monitor.collectors.anthropic import AnthropicUsageSource
from monitor.collectors.openai import OpenAIUsageSource
from monitor.config import settings
from monitor.db.upsert import unused_keys_query, upsert_key_inventory_rows
from monitor.simulator.app import create_app


def _anthropic_inventory_response() -> httpx.Response:
    client = TestClient(create_app())
    resp = client.get(
        "/anthropic/v1/organizations/api_keys",
        headers={"x-api-key": "test-key", "anthropic-version": "2023-06-01"},
    )
    return httpx.Response(
        status_code=200,
        json=resp.json(),
        request=httpx.Request(
            "GET",
            "http://testserver/anthropic/v1/organizations/api_keys",
        ),
    )


def _openai_inventory_response() -> httpx.Response:
    client = TestClient(create_app())
    projects = client.get(
        "/openai/v1/organization/projects",
        headers={"Authorization": "Bearer test-key"},
    ).json()
    all_keys = []
    for project in projects["data"]:
        keys = client.get(
            f"/openai/v1/organization/projects/{project['id']}/api_keys",
            headers={"Authorization": "Bearer test-key"},
        ).json()
        all_keys.extend(keys["data"])
    return httpx.Response(
        status_code=200,
        json={"data": all_keys},
        request=httpx.Request(
            "GET",
            "http://testserver/openai/v1/organization/projects",
        ),
    )


@pytest.fixture()
def db():
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE key_inventory, usage_fact"))
    yield engine
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE key_inventory, usage_fact"))
    engine.dispose()


class TestInventoryCollection:
    def test_anthropic_snapshot_twice_is_idempotent(self, db) -> None:
        source = AnthropicUsageSource(
            base_url="http://testserver/anthropic",
            admin_key="test-key",
            transport=httpx.MockTransport(lambda r: _anthropic_inventory_response()),
        )
        rows1 = source.list_keys()
        with db.begin() as conn:
            upsert_key_inventory_rows(conn, rows1)
            count1 = conn.execute(text("SELECT count(*) FROM key_inventory")).scalar_one()

        rows2 = source.list_keys()
        with db.begin() as conn:
            upsert_key_inventory_rows(conn, rows2)
            count2 = conn.execute(text("SELECT count(*) FROM key_inventory")).scalar_one()

        assert count1 == count2
        assert count1 > 0

    def test_openai_snapshot_twice_is_idempotent(self, db) -> None:
        source = OpenAIUsageSource(
            base_url="http://testserver/openai",
            admin_key="test-key",
            transport=httpx.MockTransport(lambda r: _openai_inventory_response()),
        )
        rows1 = source.list_keys()
        with db.begin() as conn:
            upsert_key_inventory_rows(conn, rows1)
            count1 = conn.execute(text("SELECT count(*) FROM key_inventory")).scalar_one()

        rows2 = source.list_keys()
        with db.begin() as conn:
            upsert_key_inventory_rows(conn, rows2)
            count2 = conn.execute(text("SELECT count(*) FROM key_inventory")).scalar_one()

        assert count1 == count2
        assert count1 > 0

    def test_unused_keys_query_finds_dormant_keys(self, db) -> None:
        source = AnthropicUsageSource(
            base_url="http://testserver/anthropic",
            admin_key="test-key",
            transport=httpx.MockTransport(lambda r: _anthropic_inventory_response()),
        )
        rows = source.list_keys()
        with db.begin() as conn:
            upsert_key_inventory_rows(conn, rows)
            # All keys are unused (no usage_fact rows yet)
            unused = unused_keys_query(conn, days=30)
            assert len(unused) == len(rows)
