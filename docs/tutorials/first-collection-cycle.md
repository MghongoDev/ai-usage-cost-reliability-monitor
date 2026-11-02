# First collection cycle

A single collect, probe, and rule pass, from the command line to the rows.

## 1. Collect

```bash
make collect
```

`monitor collect` fetches the trailing day of usage and inventory from both
providers and upserts them into the database. With the simulator the data is
deterministic, because the seed is fixed.

## 2. Probe

```bash
make probe
```

`monitor probe` sends one canary request to each provider and stores the
outcome, latency, and status code in `probe_result`.

## 3. Evaluate rules

```bash
make rules
```

`monitor rules` evaluates the rule set over the trailing hour and persists
alert events. Alerts that fired are written to the database; the command
prints a summary.

## 4. Read the control plane

With `monitor run` serving on `127.0.0.1:8001`, fetch the datasets:

```bash
curl http://127.0.0.1:8001/usage?limit=3
curl http://127.0.0.1:8001/cost?limit=3
curl http://127.0.0.1:8001/probes
curl http://127.0.0.1:8001/alerts?state=firing
curl http://127.0.0.1:8001/metrics
```

Each dataset endpoint returns `{"dataset": "usage", "rows": [...]}`. The
`/metrics` endpoint returns a Prometheus text digest each metric family as
a counter.

## What you should see

- `/usage` rows carry `provider`, `bucket_start`, `bucket_width`, and the
  token columns (`requests`, `input_uncached`, `input_cached`,
  `cache_creation`, `output_tokens`).
- `/cost` rows carry `provider`, `day`, and `amount_usd`.
- `/probes` rows carry `provider`, `probed_at`, `outcome`, and
  `latency_ms`.
- `/alerts?state=firing` returns the alert events raised in this cycle.
- `/metrics` returns `# TYPE monitor_usage_rows counter` families.

## Troubleshooting

If `/health` returns 503, the database is not reachable. Check that
`make up` finished and that `DATABASE_URL` points at port 55432.

If `/usage` is empty, run `make collect` and confirm the simulator is up
on port 8001.
