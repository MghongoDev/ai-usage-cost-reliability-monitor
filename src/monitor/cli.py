"""CLI entrypoint for the monitor.

Commands:
- collect    Fetch usage / inventory / costs from a provider into the data store.
- probe      Send canary probes to a provider and store the results.
- rules      Evaluate the rule set over recent state and fire alerts.
- run        Run the monitor's HTTP API (planned: separate phase).
- backfill   Seed historical usage (planned: separate phase).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import typer
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import Connection as SAConnection

import monitor.config as config
from monitor.collectors import anthropic, openai
from monitor.collectors.base import UsageSource
from monitor.db.upsert import record_collector_run, run_collection, upsert_usage_rows
from monitor.probes import runner as probe_runner
from monitor.rules import alert as alert_rule
from monitor.rules import remaining as rules_remaining
from monitor.rules.anomaly import detect_usage_anomalies

app = typer.Typer(help="Monitor CLI: collect usage, run probes, evaluate rules.")

DEFAULT_MODEL = "claude-haiku-5-5"
COLLECT_WINDOW_DAYS = 1
RULE_WINDOW_HOURS = 1

PROVIDERS = ("anthropic", "openai")

_engine: Engine | None = None


def _database_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(config.settings.database_url)
    return _engine


def _connect() -> SAConnection:
    """Open a connection from the pooled engine (SQLAlchemy style)."""
    return _database_engine().connect()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def nonempty_or_default(key: str) -> str:
    """Return a usable admin key: the supplied key, or a default if empty."""
    return key or "monitor"


def _distinct_keys(conn: SAConnection, provider: str) -> list[tuple[str, bool]]:
    """Return distinct (api_key_id, last_used_at) rows for a provider."""
    rows = conn.execute(
        text(
            "SELECT api_key_id, last_used_at FROM key_inventory "
            "WHERE provider = :p GROUP BY api_key_id, last_used_at"
        ),
        {"p": provider},
    ).fetchall()
    return [(r[0], bool(r[1])) for r in rows]


@app.command()
def collect(
    provider: str = typer.Option(
        "all",
        "--provider",
        "-p",
        case_sensitive=False,
        help="Provider to collect: anthropic, openai, or all.",
    ),
    days: int = typer.Option(1, "--days", "-d", help="Collect the last N days of usage."),
) -> None:
    """Fetch usage and inventory from the providers into the data store."""
    conn = _connect()
    try:
        providers = ("all",)
        if provider in ("anthropic", "openai"):
            providers = (provider,)
        for p in providers:
            _collect_provider(conn, p, days)
    finally:
        conn.close()


def _collect_provider(conn: SAConnection, provider: str, days: int) -> None:
    source: UsageSource
    if provider == "anthropic":
        source = anthropic.AnthropicUsageSource(
            base_url=config.settings.anthropic_base_url,
            admin_key=nonempty_or_default(config.settings.anthropic_admin_key),
        )
    else:
        source = openai.OpenAIUsageSource(
            base_url=config.settings.openai_base_url,
            admin_key=nonempty_or_default(config.settings.openai_admin_key),
        )
    end = _utcnow()
    start = end - timedelta(days=days)
    rows = run_collection(conn, source, (start.isoformat(), end.isoformat()))
    typer.echo(f"[collect] {provider}: wrote {rows} usage rows")


@app.command()
def probe() -> None:
    """Run canary probes against each provider and store the results."""
    conn = _connect()
    try:
        jobs = (
            ("anthropic", config.settings.anthropic_base_url),
            ("openai", config.settings.openai_base_url),
        )
        for provider, base_url in jobs:
            api_key = nonempty_or_default(getattr(config.settings, f"{provider}_admin_key"))
            runner = probe_runner.ProbeRunner(
                base_url=base_url,
                api_key=api_key,
                model=DEFAULT_MODEL,
                conn=conn,
            )
            result = runner.probe_once()
            typer.echo(
                f"[probe] {provider}: {result['outcome']} "
                f"({result['latency_ms']}ms, status {result['status_code']})"
            )
    finally:
        conn.close()


@app.command()
def rules(window_hours: int = typer.Option(RULE_WINDOW_HOURS, "--window-hours", "-w")) -> None:
    """Evaluate the rule set over recent state and persist alert events."""
    conn = _connect()
    try:
        end = _utcnow()
        start = end - timedelta(hours=window_hours)
        window = (start.isoformat(), end.isoformat())

        # usage-anomaly rule (Tracer 11): robust z-score on hourly buckets.
        for provider in PROVIDERS:
            try:
                for row in detect_usage_anomalies(
                    conn, window, provider=provider, bucket_width="1h"
                ):
                    _persist_alert(conn, row)
            except Exception as exc:  # noqa: BLE001
                typer.echo(f"[rules] anomaly for {provider} skipped: {exc}")

        # new-entity rule over recent key inventory snapshots.
        try:
            snapshots = [
                {
                    "provider": r[0],
                    "api_key_id": r[1],
                    "name": r[2],
                    "snapshot_date": r[3].isoformat(),
                }
                for r in conn.execute(
                    text(
                        "SELECT provider, api_key_id, name, snapshot_date "
                        "FROM key_inventory WHERE snapshot_date >= :cutoff"
                    ),
                    {"cutoff": start.isoformat()},
                ).fetchall()
            ]
            for row in rules_remaining.new_entity_rule(conn, snapshots):
                _persist_alert(conn, row)
        except Exception as exc:  # noqa: BLE001
            typer.echo(f"[rules] new_entity skipped: {exc}")

        # absence rule for each provider.
        for provider in PROVIDERS:
            for key_id, _ in _distinct_keys(conn, provider):
                try:
                    for row in rules_remaining.absence_rule(
                        conn, provider=provider, subject=key_id
                    ):
                        _persist_alert(conn, row)
                except Exception as exc:  # noqa: BLE001
                    typer.echo(f"[rules] absence for {provider}:{key_id} skipped: {exc}")

        # governance rule for each provider.
        for provider in PROVIDERS:
            try:
                for row in rules_remaining.governance_rule(conn, provider=provider):
                    _persist_alert(conn, row)
            except Exception as exc:  # noqa: BLE001
                typer.echo(f"[rules] governance for {provider} skipped: {exc}")

        typer.echo(f"[rules] evaluated window {start.isoformat()}..{end.isoformat()}")
    finally:
        conn.close()


def _persist_alert(conn: SAConnection, row: dict[str, Any]) -> None:
    """Fingerprint-based upsert of an alert event."""
    should_fire, _state, _inserted_row = alert_rule.should_fire_alert(
        conn,
        fingerprint=row["fingerprint"],
        rule_id=row["rule_id"],
        subject=row.get("subject") or "",
        severity=row.get("severity") or "info",
        eval_count=1,
        cooldown_evals=1,
        fire_limit=3,
        resolve_delay=3,
        now=_utcnow(),
    )
    if should_fire:
        alert_rule.upsert_alert_event(conn, _inserted_row)


@app.command()
def run(
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Address to bind the control-plane HTTP API.",
    ),
    port: int = typer.Option(
        8002,
        "--port",
        help="Port to bind the control-plane HTTP API.",
    ),
) -> None:
    """Run the monitor's control-plane HTTP API, serving usage, cost, and metrics."""
    from monitor.server import MonitorAPI

    app = MonitorAPI(config.settings.database_url).app
    typer.echo(f"[run] serving the monitor API on http://{host}:{port}")
    import uvicorn

    uvicorn.run(app, host=host, port=port)


def _usage_source(provider: str) -> UsageSource:
    """Build a usage source for a provider (simulator or real API)."""
    if provider == "anthropic":
        return anthropic.AnthropicUsageSource(
            base_url=config.settings.anthropic_base_url,
            admin_key=nonempty_or_default(config.settings.anthropic_admin_key),
        )
    return openai.OpenAIUsageSource(
        base_url=config.settings.openai_base_url,
        admin_key=nonempty_or_default(config.settings.openai_admin_key),
    )


@app.command()
def backfill(
    days: int = typer.Option(90, "--days", "-d", help="Backfill the trailing N days of usage."),
) -> None:
    """Re-pull historical usage windows and upsert them idempotently.

    Every run produces the same row counts, so a backfill can be repeated.
    """
    conn = _connect()
    try:
        end = _utcnow()
        for offset in range(days, 0, -1):
            start = end - timedelta(days=offset)
            window = (start.isoformat(), end.isoformat())
            for provider in PROVIDERS:
                source = _usage_source(provider)
                rows, _unknown = source.fetch_usage(window, bucket_width="1h")
                upsert_usage_rows(conn, rows)
                record_collector_run(
                    conn,
                    source="backfill",
                    window_start=start.isoformat(),
                    window_end=end.isoformat(),
                    rows_written=len(rows),
                    success=True,
                )
        typer.echo(f"[backfill] wrote historical usage for the trailing {days} days")
    finally:
        conn.close()


if __name__ == "__main__":  # pragma: no cover
    app()
