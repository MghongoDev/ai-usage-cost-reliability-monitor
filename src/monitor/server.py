"""Monitor HTTP API (control plane).

Serves collected usage, cost, inventory, probe, SLO, and alert data over
HTTP so Grafana and other dashboards can consume it. The `monitor run`
command starts this app with uvicorn.

Issue: T7-01 (Phase 7)
ADRs: 0001 (GitHub Actions cron drives collection, Render serves Grafana),
      0002 (Deployment architecture: GitHub Actions scheduler + Render free
      services)
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import Engine, create_engine, text

logger = logging.getLogger(__name__)

# Prometheus metric families emitted by GET /metrics.
_USAGE_ROWS = "monitor_usage_rows"
_COST_USD = "monitor_cost_usd"
_PROBE_OK = "monitor_probe_ok"
_PROBE_TOTAL = "monitor_probe_total"
_ACTIVE_ALERTS = "monitor_active_alerts"
_UPTIME = "monitor_uptime_seconds"

_LABEL_COMPONENT = "component"


def _row_dicts(conn: Any, stmt: Any, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Execute *stmt* with *params* and return each row as a dict."""
    return [dict(row) for row in conn.execute(stmt, params).mappings().all()]


def count_rows(conn: Any, stmt: Any, params: dict[str, Any] | None = None) -> int:
    """Return the row count for a given SQL statement."""
    if params:
        return conn.execute(stmt, params).scalar() or 0
    return conn.execute(stmt).scalar() or 0


def _database_reachable(engine: Engine) -> bool:
    """Return True only if *engine* can complete a query against the DB."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


class MonitorAPI:
    """FastAPI application serving the monitor's collected data.

    The app builds a pooled engine against *database_url* at construction
    time so routes can run read queries without a running HTTP server (the
    test suite drives it directly). `run()` hands the app to uvicorn.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._engine = create_engine(database_url)
        self._started_at = time.monotonic()
        self.app = self._build()

    def _connect(self) -> Any:
        return self._engine.connect()

    def _build(self) -> FastAPI:
        app = FastAPI(title="Monitor API", version="0.1.0")

        @app.get("/health", tags=["lifecycle"])
        def health() -> dict[str, str]:
            if _database_reachable(self._engine):
                return {"status": "ok", "database": "reachable"}
            raise HTTPException(
                status_code=503, detail={"status": "error", "database": "unreachable"}
            )

        @app.get("/metrics", tags=["observability"])
        def metrics() -> PlainTextResponse:
            return PlainTextResponse(
                self._digest(),
                status_code=200,
                media_type="text/plain; charset=utf-8",
            )

        @app.get("/usage", tags=["datasets"])
        def usage(since: str | None = Query(None), limit: int = Query(100)) -> dict[str, Any]:
            return self._serve("usage", since, limit)

        @app.get("/cost", tags=["datasets"])
        def cost(since: str | None = Query(None), limit: int = Query(100)) -> dict[str, Any]:
            return self._serve("cost", since, limit)

        @app.get("/inventory", tags=["datasets"])
        def inventory(limit: int = Query(100)) -> dict[str, Any]:
            return self._serve("inventory", None, limit)

        @app.get("/probes", tags=["datasets"])
        def probes(limit: int = Query(100)) -> dict[str, Any]:
            return self._serve("probes", None, limit)

        @app.get("/slo", tags=["datasets"])
        def slo(limit: int = Query(100)) -> dict[str, Any]:
            return self._serve("slo", None, limit)

        @app.get("/alerts", tags=["datasets"])
        def alerts(state: str | None = Query(None), limit: int = Query(100)) -> dict[str, Any]:
            return self._serve("alerts", None, limit, state=state)

        return app

    # -- request handlers ---------------------------------------------------

    def _serve(
        self,
        dataset: str,
        since: str | None,
        limit: int,
        state: str | None = None,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            if dataset == "usage":
                stmt = text(
                    """
                    SELECT provider, bucket_start, bucket_width,
                           dims_key,
                           requests, input_uncached, input_cached, cache_creation,
                           output_tokens
                    FROM usage_fact
                    WHERE bucket_start >= :since
                    ORDER BY bucket_start DESC
                    LIMIT :limit
                    """
                )
                rows = _row_dicts(conn, stmt, {"since": since, "limit": limit})
            elif dataset == "cost":
                stmt = text(
                    """
                    SELECT provider, day, scope_id, line_item,
                           amount_usd, description, cost_type
                    FROM cost_fact
                    WHERE day >= :since
                    ORDER BY day DESC, provider, scope_id
                    LIMIT :limit
                    """
                )
                rows = _row_dicts(conn, stmt, {"since": since, "limit": limit})
            elif dataset == "inventory":
                stmt = text(
                    """
                    SELECT provider, snapshot_date, api_key_id, scope_id, name,
                           status, owner, created_at, last_used_at
                    FROM key_inventory
                    ORDER BY provider, snapshot_date DESC
                    LIMIT :limit
                    """
                )
                rows = _row_dicts(conn, stmt, {"limit": limit})
            elif dataset == "probes":
                stmt = text(
                    """
                    SELECT provider, probed_at, outcome, latency_ms, status_code,
                           model, input_tokens, output_tokens, attempt_count
                    FROM probe_result
                    ORDER BY probed_at DESC
                    LIMIT :limit
                    """
                )
                rows = _row_dicts(conn, stmt, {"limit": limit})
            elif dataset == "slo":
                stmt = text(
                    """
                    SELECT provider, slo_name, "window", "start", "end",
                           availability_pct, error_budget_burn_pct
                    FROM sloe_metric
                    ORDER BY "start" DESC
                    LIMIT :limit
                    """
                )
                rows = _row_dicts(conn, stmt, {"limit": limit})
            elif dataset == "alerts":
                params: dict[str, Any] = {"limit": limit}
                if state is not None:
                    params["state"] = state
                    clause = "WHERE state = :state"
                else:
                    clause = ""
                stmt = text(
                    f"""
                    SELECT id, fingerprint, rule_id, subject, severity, state,
                           first_fired_at, last_notified_at, resolved_at, fire_count,
                           message
                    FROM alert_event
                    {clause}
                    ORDER BY first_fired_at DESC
                    LIMIT :limit
                    """
                )
                rows = _row_dicts(conn, stmt, params)
            else:  # pragma: no cover - defensive
                raise ValueError(f"unknown dataset: {dataset}")
            return {"dataset": dataset, "rows": rows}

    # -- metrics ------------------------------------------------------------

    def _digest(self) -> str:
        lines: list[str] = [
            "# HELP monitor_uptime_seconds Time since this process started.",
            "# TYPE monitor_uptime_seconds gauge",
            f"monitor_uptime_seconds {self._uptime()}\n",
            "# HELP monitor_usage_rows Total usage rows persisted, per collector.",
            f"# TYPE {_USAGE_ROWS} counter",
            "# HELP monitor_cost_usd Estimated spend in USD, per collector.",
            f"# TYPE {_COST_USD} gauge",
            "# HELP monitor_probe_ok Probe outcomes classified ok.",
            f"# TYPE {_PROBE_OK} gauge",
            "# HELP monitor_probe_total Probe attempts, per collector.",
            f"# TYPE {_PROBE_TOTAL} gauge",
            "# HELP monitor_active_alerts Open (non-resolved) alert events.",
            f"# TYPE {_ACTIVE_ALERTS} gauge",
        ]
        with self._connect() as conn:
            for provider in ("anthropic", "openai"):
                row = conn.execute(
                    text(
                        """
                        SELECT COALESCE(SUM(input_uncached), 0)
                             + COALESCE(SUM(input_cached), 0)
                             + COALESCE(SUM(cache_creation), 0)
                             + COALESCE(SUM(output_tokens), 0) AS tokens,
                             COUNT(*) AS rows
                        FROM usage_fact
                        WHERE provider = :provider
                        """
                    ),
                    {"provider": provider},
                ).fetchone()
                n_rows = row.rows or 0
                lines.append(f'{_USAGE_ROWS}{{{_LABEL_COMPONENT}="{provider}"}} {n_rows}\n')
                lines.append(
                    f'{_COST_USD}{{{_LABEL_COMPONENT}="{provider}"}} '
                    f"{self._cost_usd(conn, provider)}\n"
                )
            for family, outcome in (
                (_PROBE_OK, "ok"),
                (_PROBE_TOTAL, None),
            ):
                counts = self._probe_outcome_count(conn, outcome)
                for provider in ("anthropic", "openai"):
                    lines.append(
                        f'{family}{{{_LABEL_COMPONENT}="{provider}"}} {counts.get(provider, 0)}\n'
                    )
            lines.append(f'{_ACTIVE_ALERTS}{{state="firing"}} {self._active_firing(conn)}\n')
            lines.append(f'{_ACTIVE_ALERTS}{{state="resolved"}} {self._active_resolved(conn)}\n')
        return "".join(lines)

    def _uptime(self) -> float:
        return time.monotonic() - self._started_at

    def _cost_usd(self, conn: Any, provider: str) -> float:
        return (
            conn.execute(
                text(
                    "SELECT COALESCE(SUM(amount_usd), 0) FROM cost_fact WHERE provider = :provider"
                ),
                {"provider": provider},
            ).scalar()
            or 0.0
        )

    def _probe_outcome_count(self, conn: Any, outcome: str | None) -> dict[str, int]:
        if outcome is None:
            stmt = text("SELECT provider, COUNT(*) AS n FROM probe_result GROUP BY provider")
            rows = conn.execute(stmt).fetchall()
        else:
            rows = conn.execute(
                text(
                    """
                    SELECT provider, COUNT(*) AS n FROM probe_result
                    WHERE outcome = :outcome
                    GROUP BY provider
                    """
                ),
                {"outcome": outcome},
            ).fetchall()
        return {r.provider: (r.n or 0) for r in rows}

    def _active_firing(self, conn: Any) -> int:
        return count_rows(conn, text("SELECT COUNT(*) FROM alert_event WHERE state = 'firing'"))

    def _active_resolved(self, conn: Any) -> int:
        return count_rows(conn, text("SELECT COUNT(*) FROM alert_event WHERE state = 'resolved'"))
