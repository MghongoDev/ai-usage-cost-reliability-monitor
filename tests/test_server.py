"""Tests for the monitor HTTP API (control plane, T7-01).

The app is driven directly against a live Postgres database (the same
DATABASE_URL used by the rest of the suite) so the route handlers and the
/metrics Prometheus digest can be exercised without a running uvicorn
server.
"""

from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from monitor.config import settings
from monitor.server import (
    _ACTIVE_ALERTS as _ACTIVE_ALERTS_FAMILY,
)
from monitor.server import MonitorAPI

_engine = create_engine(settings.database_url)

_USAGE_COLS = (
    "provider, bucket_start, bucket_width, scope_id, api_key_id, model, "
    "requests, input_uncached, input_cached, cache_creation, output_tokens"
)
_COST_COLS = "provider, day, scope_id, line_item, amount_usd, description, cost_type"
_PROBE_COLS = (
    "provider, probed_at, outcome, latency_ms, status_code, model, "
    "input_tokens, output_tokens, attempt_count"
)
_ALERT_COLS = (
    "fingerprint, rule_id, subject, severity, state, first_fired_at, "
    "last_notified_at, resolved_at, fire_count, message"
)


def _seed_usage(conn: Any, rows: list[dict[str, Any]]) -> None:
    conn.execute(
        text(
            f"INSERT INTO usage_fact ({_USAGE_COLS}) "
            f"VALUES (:p, :b, :w, :s, :k, :m, :r, :i, :c, :ca, :o)"
        ),
        rows,
    )


def _seed() -> None:
    conn = _engine.connect()
    try:
        with conn.begin():
            # Seed param aliases: p=provider b=bucket_start w=bucket_width s=scope_id
            # k=api_key_id m=model r=requests i=input_uncached c=input_cached
            # ca=cache_creation o=output_tokens
            # cost: d=day l=line_item a=amount_usd dsc=description t=cost_type
            # probe: t=probed_at o=outcome l=latency_ms s=status_code m=model
            # i=input_tokens o2=output_tokens a=attempt_count
            # alert: f=fingerprint r=rule_id s=subject sv=severity st=state
            # f1=first_fired_at l1=last_notified_at r1=resolved_at c=fire_count m=message
            conn.execute(text("TRUNCATE usage_fact, cost_fact, probe_result, alert_event"))
            _seed_usage(
                conn,
                [
                    {
                        "p": "anthropic",
                        "b": "2026-10-01T00:00:00+00:00",
                        "w": "1h",
                        "s": "scope-a",
                        "k": "key-a",
                        "m": "claude-haiku-5-5",
                        "r": 10,
                        "i": 100,
                        "c": 200,
                        "ca": 50,
                        "o": 300,
                    },
                    {
                        "p": "anthropic",
                        "b": "2026-10-01T01:00:00+00:00",
                        "w": "1h",
                        "s": "scope-a",
                        "k": "key-a",
                        "m": "claude-haiku-5-5",
                        "r": 5,
                        "i": 50,
                        "c": 0,
                        "ca": 0,
                        "o": 80,
                    },
                    {
                        "p": "openai",
                        "b": "2026-10-01T00:00:00+00:00",
                        "w": "1h",
                        "s": "scope-b",
                        "k": "key-b",
                        "m": "gpt-5",
                        "r": 20,
                        "i": 300,
                        "c": 0,
                        "ca": 0,
                        "o": 500,
                    },
                ],
            )
            conn.execute(
                text(f"INSERT INTO cost_fact ({_COST_COLS}) VALUES (:p, :d, :s, :l, :a, :dsc, :t)"),
                [
                    {
                        "p": "anthropic",
                        "d": "2026-10-01",
                        "s": "scope-a",
                        "l": "key-a",
                        "a": 0.42,
                        "dsc": "usage",
                        "t": "usage",
                    },
                    {
                        "p": "anthropic",
                        "d": "2026-10-01",
                        "s": "scope-a",
                        "l": "key-b",
                        "a": 0.08,
                        "dsc": "tax",
                        "t": "usage",
                    },
                ],
            )
            conn.execute(
                text(
                    f"INSERT INTO probe_result ({_PROBE_COLS}) "
                    f"VALUES (:p, :t, :o, :l, :s, :m, :i, :o2, :a)"
                ),
                [
                    {
                        "p": "anthropic",
                        "t": "2026-10-01T00:00:00+00:00",
                        "o": "ok",
                        "l": 12,
                        "s": 200,
                        "m": "claude-haiku-5-5",
                        "i": 5,
                        "o2": 5,
                        "a": 1,
                    },
                    {
                        "p": "anthropic",
                        "t": "2026-10-01T00:00:00+00:00",
                        "o": "network",
                        "l": 50,
                        "s": 504,
                        "m": "claude-haiku-5-5",
                        "i": 5,
                        "o2": 5,
                        "a": 2,
                    },
                    {
                        "p": "openai",
                        "t": "2026-10-01T00:00:00+00:00",
                        "o": "ok",
                        "l": 18,
                        "s": 200,
                        "m": "gpt-5",
                        "i": 5,
                        "o2": 5,
                        "a": 1,
                    },
                ],
            )
            conn.execute(
                text(
                    f"INSERT INTO alert_event ({_ALERT_COLS}) "
                    f"VALUES (:f, :r, :s, :sv, :st, :f1, :l1, :r1, :c, :m)"
                ),
                [
                    {
                        "f": "firing.example",
                        "r": "budget.projection",
                        "s": "scope-a",
                        "sv": "info",
                        "st": "firing",
                        "f1": "2026-10-01T00:00:00+00:00",
                        "l1": None,
                        "r1": None,
                        "c": 1,
                        "m": "over budget",
                    },
                    {
                        "f": "resolved.example",
                        "r": "new_entity",
                        "s": "key-b",
                        "sv": "info",
                        "st": "resolved",
                        "f1": "2026-09-01T00:00:00+00:00",
                        "l1": "2026-09-02T00:00:00+00:00",
                        "r1": "2026-09-02T00:00:00+00:00",
                        "c": 2,
                        "m": "resolved",
                    },
                ],
            )
    finally:
        conn.close()


@pytest.fixture(scope="module")
def api() -> Generator[MonitorAPI, Any, Any]:
    app = MonitorAPI(settings.database_url)
    yield app
    app._engine.dispose()


@pytest.fixture()
def seeded() -> None:
    _seed()


def _client(api: MonitorAPI) -> TestClient:
    return TestClient(api.app)


class TestHealth:
    def test_returns_reachable(self, api: MonitorAPI) -> None:
        response = _client(api).get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "reachable"}


class TestMetrics:
    def test_digest_format(self, api: MonitorAPI, seeded: None) -> None:
        response = _client(api).get("/metrics")
        assert response.status_code == 200
        text = response.text
        assert text.startswith("# HELP monitor_usage_rows")
        assert "# TYPE monitor_usage_rows counter" in text
        assert "# TYPE monitor_cost_usd counter" in text
        assert "# TYPE monitor_probe_ok counter" in text
        assert "# TYPE monitor_probe_total counter" in text
        assert f"# TYPE {_ACTIVE_ALERTS_FAMILY} counter" in text

    def test_usage_rows_counted_per_provider(self, api: MonitorAPI, seeded: None) -> None:
        response = _client(api).get("/metrics")
        text = response.text
        assert 'monitor_usage_rows{component="anthropic"} 2' in text
        assert 'monitor_usage_rows{component="openai"} 1' in text

    def test_cost_usd_per_provider(self, api: MonitorAPI, seeded: None) -> None:
        response = _client(api).get("/metrics")
        text = response.text
        assert 'monitor_cost_usd{component="anthropic"} 0.5' in text

    def test_probe_outcomes(self, api: MonitorAPI, seeded: None) -> None:
        response = _client(api).get("/metrics")
        text = response.text
        assert 'monitor_probe_ok{component="anthropic"} 1' in text
        assert 'monitor_probe_ok{component="openai"} 1' in text
        assert 'monitor_probe_total{component="anthropic"} 2' in text
        assert 'monitor_probe_total{component="openai"} 1' in text

    def test_active_alerts_split(self, api: MonitorAPI, seeded: None) -> None:
        response = _client(api).get("/metrics")
        text = response.text
        assert 'monitor_active_alerts{state="firing"} 1' in text
        assert 'monitor_active_alerts{state="resolved"} 1' in text


class TestDatasets:
    def test_usage_rows(self, api: MonitorAPI, seeded: None) -> None:
        response = _client(api).get("/usage", params={"since": "2026-09-01", "limit": "10"})
        assert response.status_code == 200
        body = response.json()
        assert body["dataset"] == "usage"
        assert len(body["rows"]) == 3
        assert body["rows"][0]["provider"] == "anthropic"

    def test_usage_uses_since_limit(self, api: MonitorAPI, seeded: None) -> None:
        response = _client(api).get("/usage", params={"since": "2026-10-01", "limit": "1"})
        body = response.json()
        assert len(body["rows"]) == 1
        assert body["rows"][0]["provider"] == "anthropic"

    def test_cost_rows(self, api: MonitorAPI, seeded: None) -> None:
        response = _client(api).get("/cost", params={"since": "2026-09-01"})
        assert response.status_code == 200
        body = response.json()
        assert body["dataset"] == "cost"
        assert len(body["rows"]) == 2

    def test_inventory_rows(self, api: MonitorAPI, seeded: None) -> None:
        response = _client(api).get("/inventory")
        assert response.status_code == 200
        body = response.json()
        assert body["dataset"] == "inventory"
        assert isinstance(body["rows"], list)

    def test_probes_rows(self, api: MonitorAPI, seeded: None) -> None:
        response = _client(api).get("/probes")
        assert response.status_code == 200
        body = response.json()
        assert body["dataset"] == "probes"
        assert len(body["rows"]) == 3

    def test_slo_rows(self, api: MonitorAPI, seeded: None) -> None:
        response = _client(api).get("/slo")
        assert response.status_code == 200
        body = response.json()
        assert body["dataset"] == "slo"
        assert isinstance(body["rows"], list)

    def test_alerts_rows(self, api: MonitorAPI, seeded: None) -> None:
        response = _client(api).get("/alerts")
        assert response.status_code == 200
        body = response.json()
        assert body["dataset"] == "alerts"
        states = {row["state"] for row in body["rows"]}
        assert {"firing", "resolved"} <= states

    def test_alerts_filter_by_state(self, api: MonitorAPI, seeded: None) -> None:
        response = _client(api).get("/alerts", params={"state": "firing"})
        body = response.json()
        assert {row["state"] for row in body["rows"]} == {"firing"}
