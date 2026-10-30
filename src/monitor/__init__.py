"""Self-hosted usage, cost, and reliability monitor for AI provider admin APIs.

Tracers:
- Tracer 01: Normalized schema and migrations (closed)
- Tracer 02: Anthropic usage, end to end (closed)
- Tracer 03: OpenAI usage, end to end (closed)
- Tracer 04: Key and scope inventory, both providers (closed)
- Tracer 05: Price table and per-key cost estimation (closed)
- Tracer 06: Reconciliation and budgets (closed)
- Tracer 07: Probe runner and availability (closed)
- Tracer 08: SLOs and error-budget burn (closed)
- Tracer 09: Scenario injection on the simulator (closed)
- Tracer 10: Alert lifecycle plus budget-projection rule (closed)
- Tracer 11: Usage-anomaly rule (closed)
- Tracer 12: Remaining rules (closed)
- Tracer 13: Backtest harness (closed)
- Tracer 14: Grafana provisioning (closed)
- Tracer 15: Deploy (Render) (closed)
- Tracer 16: Ops hardening (dumps, keepalive, weekly report, runbooks) (closed)
"""

__version__ = "0.1.0"

# Submodules
from monitor.collectors import (
    anthropic,
    base,
    constants,
    cost,
    models,
    normalize,
    normalize_openai,
    openai,
)
from monitor.config import settings
from monitor.db import schema, upsert
from monitor.probes import (
    AVAILABILITY_SLO,
    FAST_WINDOW,
    SLOW_WINDOW,
    classify_outcome,
    compute_availability,
    compute_error_budget_burn,
    compute_fast_window,
    compute_slow_window,
    get_sloe_metrics,
    record_sloe_metrics,
)
from monitor.rules import (
    STATE_FIRING,
    STATE_PENDING,
    STATE_RESOLVED,
    absence_rule,
    detect_usage_anomalies,
    governance_rule,
    new_entity_rule,
    slo_burn_rule,
)
from monitor.rules.alert import (
    evaluate_budget_projection_rule,
    get_firing_alerts,
    should_fire_alert,
    upsert_alert_event,
)
from monitor.simulator import (
    anthropic as simulator_anthropic,
)
from monitor.simulator import (
    app,
)
from monitor.simulator import (
    constants as sim_constants,
)
from monitor.simulator import (
    openai as simulator_openai,
)
from monitor.simulator.scenarios import (
    active_scenarios,
    all_scenarios,
    get_scenario,
)

__all__ = [
    "__version__",
    "anthropic",
    "base",
    "constants",
    "cost",
    "models",
    "normalize",
    "normalize_openai",
    "openai",
    "normalize_openai_keys_payload",
    "normalize_anthropic_keys_payload",
    "normalize_anthropic_key",
    "normalize_openai_key",
    "settings",
    "schema",
    "upsert",
    "classify_outcome",
    "compute_availability",
    "AVAILABILITY_SLO",
    "FAST_WINDOW",
    "SLOW_WINDOW",
    "compute_fast_window",
    "compute_slow_window",
    "compute_error_budget_burn",
    "get_sloe_metrics",
    "record_sloe_metrics",
    "detect_usage_anomalies",
    "absence_rule",
    "governance_rule",
    "new_entity_rule",
    "slo_burn_rule",
    "evaluate_budget_projection_rule",
    "get_firing_alerts",
    "should_fire_alert",
    "upsert_alert_event",
    "STATE_PENDING",
    "STATE_FIRING",
    "STATE_RESOLVED",
    "app",
    "simulator_anthropic",
    "simulator_openai",
    "sim_constants",
    "active_scenarios",
    "all_scenarios",
    "get_scenario",
]
