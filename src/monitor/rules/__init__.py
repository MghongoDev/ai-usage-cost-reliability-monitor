"""Rule engine: pure functions over database state, unit-testable.

Rule types:
- usage.anomaly: robust_z-score on hourly buckets (Tracer 11)
- budget.projection: projected month-end spend > budget (Tracer 10)
- new_entity: new key or model appears (Tracer 12)
- absence: collector staleness or dormant key (Tracer 12)
- governance: key naming/ownership convention violations (Tracer 12)
- slo.burn: SLO error-budget burn rate (Tracer 12)

Each rule returns a list of alert row dicts ready for insertion into
alert_event. Pure functions, no side effects.

Alert lifecycle (see alert module for function implementations):
- fingerprint-based deduplication
- cooldown, resolve notices, reminders
- state machine: pending -> firing -> resolved
"""

from monitor.rules.anomaly import detect_usage_anomalies
from monitor.rules.remaining import (
    absence_rule,
    governance_rule,
    new_entity_rule,
    slo_burn_rule,
)

# Alert state values (shared across rules and the alert lifecycle)
STATE_PENDING = "pending"
STATE_FIRING = "firing"
STATE_RESOLVED = "resolved"

__all__ = [
    "detect_usage_anomalies",
    "absence_rule",
    "governance_rule",
    "new_entity_rule",
    "slo_burn_rule",
    "STATE_PENDING",
    "STATE_FIRING",
    "STATE_RESOLVED",
]
