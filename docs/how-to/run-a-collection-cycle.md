# Run a collection cycle

A cycle is one pass of collect, probe, and rule evaluation. This guide shows
the commands and the state they produce.

## Why three steps

The system is split into three independent jobs. Collect fetches the data,
probe measures the live service, and rules compare the data against
conditions. Splitting them lets the scheduler run each at its own cadence
and keeps a single failure from stopping the others.

## Run all three steps

```bash
make collect
make probe
make rules
```

## Run them in one command

```bash
make demo
```

`make demo` starts the stack, applies the migrations, collects, and runs
the control plane. Use it for a first run, not for repeated cycles.

## What each step does

### collect

```bash
uv run monitor collect --provider all --days 1
```

Fetches the trailing day of usage and inventory from the configured
providers. With the simulator the data is the same every time, because the
seed is fixed.

### probe

```bash
uv run monitor probe
```

Sends one canary request per provider and persists the outcome, latency,
and status code in `probe_result`. A probe failure is stored, not raised.

### rules

```bash
uv run monitor rules --window-hours 1
```

Evaluates the rule set over the trailing hour and persists alert events.
Normal rules stay silent; rules that fire persist alert events and print a
summary.

## What changes in the database

- `usage_fact` gains new buckets.
- `probe_result` gains a new row.
- `alert_event` gains rows when a rule fires.

## Read it back

```bash
curl http://127.0.0.1:8001/usage?limit=5
curl http://127.0.0.1:8001/cost?limit=5
curl http://127.0.0.1:8001/probes
curl http://127.0.0.1:8001/alerts?state=firing
```

## Next steps

- [Debug a probe](debug-a-probe.md) if a probe fails or reports a bad
  outcome.
- [Add a rule](add-a-new-rule.md) to change what the rule engine evaluates.
- See the control-plane reference for the HTTP endpoints.
