"""CLI commands leave committed rows behind (issue #35).

The tests invoke the commands themselves and read the result through a separate
connection, so a command that only writes inside a rolled-back transaction fails.
"""

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from typer.testing import CliRunner

import monitor.cli as cli
from monitor.collectors.anthropic import AnthropicUsageSource
from monitor.collectors.openai import OpenAIUsageSource
from monitor.config import settings
from monitor.simulator.app import create_app

DATABASE_URL = settings.database_url
_READ_ENGINE = create_engine(DATABASE_URL)


def _read_connect():
    return _READ_ENGINE.connect()


def _read_begin():
    return _READ_ENGINE.begin()


class FakeSource:
    """A usage source that records the windows it is asked for."""

    provider = "anthropic"
    usage_endpoint = "/usage"
    cost_endpoint = "/cost"
    keys_endpoint = "/keys"

    def __init__(
        self,
        provider: str = "anthropic",
        base_url: str = "",
        admin_key: str = "",
        transport: Any = None,
    ) -> None:
        self.provider = provider
        self.windows: list[tuple[tuple[str, str], str]] = []
        self.last_raw_response: dict[str, Any] | None = {"data": []}

    def fetch_usage(
        self, window: tuple[str | int, str | int], bucket_width: str = "1h"
    ) -> tuple[list[dict[str, Any]], int]:
        self.windows.append((window, bucket_width))  # type: ignore[arg-type]
        return (
            [
                {
                    "provider": self.provider,
                    "bucket_start": "2026-11-17T10:00:00+00:00",
                    "bucket_width": bucket_width,
                    "scope_id": "scope-1",
                    "api_key_id": "key-1",
                    "model": "model-1",
                    "requests": 1,
                    "input_uncached": 1,
                    "input_cached": 0,
                    "cache_creation": 0,
                    "output_tokens": 1,
                    "extra": {},
                }
            ],
            0,
        )

    def fetch_costs(self, window: tuple[str | int, str | int]) -> list[dict[str, Any]]:
        return [
            {
                "provider": self.provider,
                "day": "2026-11-17",
                "scope_id": "scope-1",
                "line_item": "usage",
                "amount_usd": 1.0,
                "description": "usage",
                "cost_type": None,
            }
        ]

    def list_keys(self) -> list[dict[str, Any]]:
        return [
            {
                "provider": self.provider,
                "api_key_id": f"key-{self.provider}",
                "scope_id": "scope-1",
                "name": "a key",
                "status": "active",
                "owner": "owner-1",
                "created_at": "2026-11-01T00:00:00+00:00",
                "last_used_at": None,
                "extra": {},
            }
        ]


@pytest.fixture()
def db(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cli.config.settings, "database_url", DATABASE_URL)
    monkeypatch.setattr(cli, "_engine", None)
    engine = create_engine(DATABASE_URL)
    tables = (
        "usage_fact",
        "cost_fact",
        "key_inventory",
        "collector_run",
        "raw_payload",
        "probe_result",
        "alert_event",
    )
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))
    yield engine
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))
    engine.dispose()


def test_collect_leaves_usage_rows_behind(db, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.anthropic, "AnthropicUsageSource", FakeSource)

    result = CliRunner().invoke(cli.app, ["collect", "--provider", "anthropic"])

    assert result.exit_code == 0, result.output
    with _read_connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM usage_fact")).scalar_one()
    assert count > 0


def test_run_collection_labels_rows_with_the_source_provider(db) -> None:
    from monitor.db.upsert import run_collection

    source = FakeSource(provider="openai")
    source.usage_endpoint = "/v1/organization/usage/completions"
    window = ("2026-11-17T10:00:00+00:00", "2026-11-17T11:00:00+00:00")

    with _read_begin() as conn:
        run_collection(conn, source, window)
        run_source = conn.execute(
            text("SELECT source FROM collector_run ORDER BY id DESC LIMIT 1")
        ).scalar_one()
        payload = conn.execute(
            text("SELECT provider, endpoint FROM raw_payload ORDER BY id DESC LIMIT 1")
        ).one()

    assert run_source == "openai.usage"
    assert payload.provider == "openai"
    assert payload.endpoint == "/v1/organization/usage/completions"


def test_collect_defaults_to_a_48_hour_window(db, monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime

    created: list[FakeSource] = []

    def source_factory(**kwargs: Any) -> FakeSource:
        source = FakeSource(provider="anthropic")
        created.append(source)
        return source

    monkeypatch.setattr(cli.anthropic, "AnthropicUsageSource", source_factory)

    result = CliRunner().invoke(cli.app, ["collect", "--provider", "anthropic"])

    assert result.exit_code == 0, result.output
    start, end = created[0].windows[0][0]
    span = datetime.fromisoformat(str(end)) - datetime.fromisoformat(str(start))
    assert span.total_seconds() == 48 * 3600


def test_backfill_windows_do_not_overlap(db, monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime

    sources: dict[str, list[FakeSource]] = {"anthropic": [], "openai": []}

    def usage_source(provider: str) -> FakeSource:
        source = FakeSource(provider=provider)
        sources[provider].append(source)
        return source

    monkeypatch.setattr(cli, "_usage_source", usage_source)

    result = CliRunner().invoke(cli.app, ["backfill", "--days", "3"])

    assert result.exit_code == 0, result.output
    windows = [window for source in sources["anthropic"] for window in source.windows]
    assert len(windows) == 3
    for ((_start, end), _), ((next_start, _), _) in zip(windows, windows[1:], strict=False):
        assert datetime.fromisoformat(str(end)) == datetime.fromisoformat(str(next_start))


def test_collect_writes_usage_cost_and_inventory_for_both_providers(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli.anthropic,
        "AnthropicUsageSource",
        lambda **kwargs: FakeSource(provider="anthropic"),
    )
    monkeypatch.setattr(
        cli.openai,
        "OpenAIUsageSource",
        lambda **kwargs: FakeSource(provider="openai"),
    )

    result = CliRunner().invoke(cli.app, ["collect"])

    assert result.exit_code == 0, result.output
    with _read_connect() as conn:
        for table in ("usage_fact", "cost_fact", "key_inventory"):
            providers = {
                row[0] for row in conn.execute(text(f"SELECT DISTINCT provider FROM {table}"))
            }
            assert providers == {"anthropic", "openai"}, table


def test_collect_twice_leaves_identical_nonzero_counts(db, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli.anthropic,
        "AnthropicUsageSource",
        lambda **kwargs: FakeSource(provider="anthropic"),
    )
    monkeypatch.setattr(
        cli.openai,
        "OpenAIUsageSource",
        lambda **kwargs: FakeSource(provider="openai"),
    )
    runner = CliRunner()
    tables = ("usage_fact", "cost_fact", "key_inventory")

    def counts() -> dict[str, int]:
        with _read_connect() as conn:
            return {
                table: conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                for table in tables
            }

    assert runner.invoke(cli.app, ["collect"]).exit_code == 0
    first = counts()
    assert runner.invoke(cli.app, ["collect"]).exit_code == 0
    second = counts()

    assert first == second
    assert all(count > 0 for count in first.values())


def test_backfill_records_the_windows_it_actually_pulled(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_usage_source", lambda provider: FakeSource(provider))

    result = CliRunner().invoke(cli.app, ["backfill", "--days", "3"])

    assert result.exit_code == 0, result.output
    with _read_connect() as conn:
        runs = conn.execute(
            text(
                "SELECT DISTINCT window_start, window_end FROM collector_run "
                "WHERE source = 'backfill' ORDER BY window_start"
            )
        ).fetchall()
    assert len(runs) == 3
    for (_, end), (next_start, _) in zip(runs, runs[1:], strict=False):
        assert end == next_start


class FakeProbeRunner:
    def __init__(self, conn, **kwargs: Any) -> None:
        self.conn = conn

    def probe_once(self) -> dict[str, Any]:
        self.conn.execute(
            text(
                "INSERT INTO probe_result "
                "(provider, probed_at, outcome, latency_ms, status_code, model, attempt_count) "
                "VALUES ('anthropic', now(), 'ok', 1, 200, 'model', 1)"
            )
        )
        return {"outcome": "ok", "latency_ms": 1, "status_code": 200}


def test_probe_leaves_rows_behind(db, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.probe_runner, "ProbeRunner", FakeProbeRunner)

    result = CliRunner().invoke(cli.app, ["probe"])

    assert result.exit_code == 0, result.output
    with _read_connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM probe_result")).scalar_one()
    assert count >= 2


def test_rules_leave_alert_rows_behind(db, monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import UTC, datetime

    def anomalies(conn, window, provider, bucket_width):
        return [
            {
                "fingerprint": f"fp-{provider}",
                "rule_id": "usage-anomaly",
                "subject": "scope-1",
                "severity": "warn",
            }
        ]

    def should_fire(conn, **kwargs):
        row = {
            "fingerprint": kwargs["fingerprint"],
            "rule_id": kwargs["rule_id"],
            "subject": kwargs["subject"],
            "severity": kwargs["severity"],
            "state": "firing",
            "first_fired_at": datetime.now(UTC),
            "message": "anomaly",
        }
        return True, "firing", row

    def upsert_alert(conn, row):
        conn.execute(
            text(
                "INSERT INTO alert_event "
                "(fingerprint, rule_id, subject, severity, state, first_fired_at, message) "
                "VALUES (:fingerprint, :rule_id, :subject, :severity, :state, "
                ":first_fired_at, :message)"
            ),
            row,
        )

    monkeypatch.setattr(cli, "detect_usage_anomalies", anomalies)
    monkeypatch.setattr(cli.alert_rule, "should_fire_alert", should_fire)
    monkeypatch.setattr(cli.alert_rule, "upsert_alert_event", upsert_alert)

    result = CliRunner().invoke(cli.app, ["rules"])

    assert result.exit_code == 0, result.output
    with _read_connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM alert_event")).scalar_one()
    assert count >= 2


def test_collect_twice_against_simulator_leaves_identical_counts(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    sim_client = TestClient(create_app())

    def simulator_transport(request: httpx.Request) -> httpx.Response:
        response = sim_client.request(
            request.method,
            request.url.path,
            params=dict(request.url.params),
            content=request.content,
            headers=dict(request.headers),
        )
        return httpx.Response(response.status_code, json=response.json(), request=request)

    monkeypatch.setattr(
        cli.anthropic,
        "AnthropicUsageSource",
        lambda **kwargs: AnthropicUsageSource(
            base_url="http://sim/anthropic",
            admin_key="test-key",
            transport=httpx.MockTransport(simulator_transport),
        ),
    )
    monkeypatch.setattr(
        cli.openai,
        "OpenAIUsageSource",
        lambda **kwargs: OpenAIUsageSource(
            base_url="http://sim/openai",
            admin_key="test-key",
            transport=httpx.MockTransport(simulator_transport),
        ),
    )
    monkeypatch.setattr(cli, "_utcnow", lambda: datetime(2026, 11, 17, 12, 0, tzinfo=UTC))

    runner = CliRunner()
    tables = ("usage_fact", "cost_fact", "key_inventory")

    def counts() -> dict[str, int]:
        with _read_connect() as conn:
            return {
                table: conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                for table in tables
            }

    assert runner.invoke(cli.app, ["collect"]).exit_code == 0
    first = counts()
    assert runner.invoke(cli.app, ["collect"]).exit_code == 0
    second = counts()

    assert first == second
    assert all(count > 0 for count in first.values())
