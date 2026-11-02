# Alert evaluation table

The backtest harness (`src/monitor/backtest.py`) runs the full pipeline
(collector, probe, rules) over the injected simulator scenarios, plus 30
clean days, and records, per incident: whether it alerted, the detection
delay, and which rule caught it.

The false-alert budget on clean data is 10. The table is the honest
measurement of alert quality: do not extend thresholds on memory alone —
run a backtest on one seed and review the table on another.

## How to run

```bash
uv run monitor rules
```

For the full backtest harness:

```bash
uv run python -m monitor.backtest
```

The per-incident table lands in this file after a backtest run.

## Contract

Each injected incident must either alert with a measured delay, or be
documented as a known miss with the rule that would catch it. The
false-alert count on the clean period must fall within the budget committed
before looking.
