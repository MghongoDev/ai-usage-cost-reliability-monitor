# Generate the weekly report

The weekly report is a Markdown summary of the previous week's monitoring
results. It is generated and committed by `scripts/weekly_report.py`.

## Generate

```bash
make weekly-report
```

or:

```bash
uv run scripts/weekly_report.py
```

## What the report contains

- Pipeline run count and success rate.
- Alert counts by rule and severity.
- Reconciliation summary (estimated vs billed cost).
- SLO burn summary.
- Backtest evaluation summary (per incident: alerted, detection delay, rule
  caught; false-alert budget).

The report is written to `docs/reports/weekly-<date>.md` and committed as
the "weekly report: <date>" commit.
