# Control-plane HTTP API reference

`monitor run` starts a FastAPI app (the **control plane**) that serves the
collected data, probes, and metrics so Grafana and the weekly report can
read them. It is documented here as a single reference.

## Start the server

```bash
make run
```

Binds to `127.0.0.1:8001` by default. Set `--host` and `--port` to change.

## Endpoints

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/health` | GET | Server and database reachability |
| `/metrics` | GET | Prometheus text digest for Grafana |
| `/usage` | GET | Time-bucketed usage, newest first |
| `/cost` | GET | Daily cost, USD, newest first |
| `/inventory` | GET | Key and scope inventory snapshots |
| `/probes` | GET | Canary probe results |
| `/slo` | GET | SLO metrics and error-budget burn |
| `/alerts` | GET | Alert events, filtered by state |

Every dataset endpoint returns the same JSON envelope:

```json
{
  "dataset": "usage",
  "rows": [ ... ]
}
```

## Endpoint reference

### GET /health

Checks that the server is up and the database is reachable. Returns:

- `200` with `{"status": "ok", "database": "reachable"}` when `SELECT 1`
  answers.
- `503` with `{"status": "error", "database": "unreachable"}` when the
  database does not answer.

The route probes the database before returning success (see the health
route's `SELECT 1`).

### GET /metrics

The Prometheus text digest Grafana reads. Each metric family is a counter:

```
# HELP monitor_usage_rows Total usage rows persisted, per collector.
# TYPE monitor_usage_rows counter
monitor_usage_rows{component="anthropic"} 1234
monitor_usage_rows{component="openai"} 567

# HELP monitor_cost_usd Estimated spend in USD, per collector.
# TYPE monitor_cost_usd counter
monitor_cost_usd{component="anthropic"} 123.45

# HELP monitor_probe_ok Probe outcomes classified ok.
# TYPE monitor_probe_ok counter
monitor_probe_ok{component="anthropic"} 9

# HELP monitor_probe_total Probe attempts.
# TYPE monitor_probe_total counter
monitor_probe_total{component="openai"} 10

# HELP monitor_active_alerts Open (non-resolved) alert events.
# TYPE monitor_active_alerts counter
monitor_active_alerts{state="firing"} 2
monitor_active_alerts{state="resolved"} 1
```

### GET /usage

Time-bucketed usage. Query parameters:

- `since` (optional): rows from this bucket onward (RFC 3339 UTC).
- `limit` (default 100).

Rows: `provider`, `bucket_start`, `bucket_width`, `dims_key`,
`requests`, `input_uncached`, `input_cached`, `cache_creation`,
`output_tokens`.

### GET /cost

Daily cost, in USD. Query parameters:

- `since` (optional).
- `limit` (default 100).

Rows: `provider`, `day`, `scope_id`, `line_item`, `amount_usd`,
`description`, `cost_type`.

### GET /inventory

Key and scope inventory snapshots. Query parameter:

- `limit` (default 100).

Rows: `provider`, `snapshot_date`, `api_key_id`, `scope_id`, `name`,
`status`, `owner`, `created_at`, `last_used_at`.

### GET /probes

Canary probe results. Query parameter:

- `limit` (default 100).

Rows: `provider`, `probed_at`, `outcome`, `latency_ms`, `status_code`,
`model`, `input_tokens`, `output_tokens`, `attempt_count`.

### GET /slo

SLO metrics (see `src/monitor/probes/slo.py`). Query parameter:

- `limit` (default 100).

Rows: `provider`, `slo_name`, `window`, `start`, `end`,
`availability_pct`, `error_budget_burn_pct`.

### GET /alerts

Alert events. Query parameters:

- `state` (optional): `firing` or `resolved`. When omitted, all states
  return.
- `limit` (default 100).

Rows: `id`, `fingerprint`, `rule_id`, `subject`, `severity`, `state`,
`first_fired_at`, `last_notified_at`, `resolved_at`, `fire_count`,
`message`.

## Notes

- Dataset endpoints return newest rows first.
- Metric families count rows persisted, not rows in a single request.
- `/alerts` uses the literal `state` values from `alert_event`: `firing`
  and `resolved`.
