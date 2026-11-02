# Monitoring cost

The monitor estimates cost from usage, not from the billing APIs alone.
Usage reports give token counts; cost reports give billed USD. The
difference is per-key attribution, which the system estimates, and
reconciliation, which the system measures.

## How cost is estimated

The collector stores usage in `usage_fact` with token counts broken into
token classes: uncached input, cached input, cache creation, and output.
`price_table` stores the price per million tokens for each model and class.
The estimated cost of a row is:

```
input_uncached * price_input_uncached / 1000000
+ input_cached * price_input_cached / 1000000
+ cache_creation * price_cache_creation / 1000000
+ output_tokens * price_output / 1000000
```

Models with no price row are marked `unpriced`, never zero.

## Reconciliation

`reconciliation_query` sums the estimated cost per scope per day and
compares it to the billed cost in `cost_fact`, returning a percentage
error. A large, stable error means the price table is missing a model or
class and should be extended, not that the estimator is wrong.

## What the billing APIs do not report

- Token counts per key. The usage endpoint reports per-key tokens; the
  cost endpoint reports org-level dollars. Per-key cost is estimated, then
  reconciled against the cost total.
- Availability and latency. The billing APIs do not probe the service. The
  simulator and the collector's probe job fill this gap.
- Per-key availability where keys are not attributable. Console usage has
  no key and counts as unknown.

## Data freshness

Usage and cost data appears within a few minutes of the API call
completing. The scheduler re-pulls the trailing window on every cycle, so
the dashboards are always a few minutes behind the providers.
