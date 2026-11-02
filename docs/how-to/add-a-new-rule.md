# Add a rule

Rules are the conditions the monitor evaluates to raise alerts. This guide
shows how to add a new one.

## Where rules live

The rule set is in `src/monitor/rules/`. Rule helpers live in their own
modules, and `src/monitor/rules/__init__.py` lists the public names plus
the alert-state constants.

## The rule contract

A rule is a pure function over database state:

- it takes a database connection and the current window (and usually a
  `provider`);
- it reads from the fact tables and reference tables;
- it yields a list of alert row dicts, or an empty list when the condition
  does not hold.

An alert row dict has at least these keys:

| Key | Purpose |
| --- | --- |
| rule_id | the rule's identity |
| subject | the entity the rule watched (scope, key, model) |
| severity | info, warning, or critical |
| message | what happened |
| fingerprint | rule plus subject, used for deduplication |

The rule engine handles the rest of the lifecycle: fingerprint
deduplication, the pending-to-firing transition, cooldown, and
resolve-delay.

Current rules:

| rule_id | What it watches | Tracer |
| --- | --- | --- |
| usage.anomaly | Robust z-score on hourly usage buckets | 11 |
| budget.projection | Projected month-end spend above budget | 10 |
| new_entity | A new key or model appears | 12 |
| absence | A collector is stale or a key is dormant | 12 |
| governance | Key naming or ownership convention violations | 12 |
| slo.burn | SLO error-budget burn rate | 12 |

## Add the rule

1. Create the rule in its own module under `src/monitor/rules/`.
2. Export it from `src/monitor/rules/__init__.py`.
3. Call it from the rule loop in `src/monitor/cli.py` so it runs each
   cycle.
4. Add a test that feeds known state and asserts the alert rows it
   produces.

## Verify

Run the rules and check the alerts:

```bash
uv run monitor rules --window-hours 1
curl http://127.0.0.1:8001/alerts?state=firing
```

A rule that fires every cycle has no resolve condition. A rule that never
fires is waiting for a signal it does not yet track.

## Related

- The rule reference describes each rule in the current set.
- The test suite shows the shape of a rule test.
