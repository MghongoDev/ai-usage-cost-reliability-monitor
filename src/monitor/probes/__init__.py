"""Probe runner and availability measurement."""

from monitor.probes.classify import classify_outcome, compute_availability
from monitor.probes.slo import (
    AVAILABILITY_SLO,
    FAST_WINDOW,
    SLOW_WINDOW,
    compute_error_budget_burn,
    compute_fast_window,
    compute_slow_window,
    get_sloe_metrics,
    record_sloe_metrics,
)

__all__ = [
    "classify_outcome",
    "compute_availability",
    "AVAILABILITY_SLO",
    "FAST_WINDOW",
    "SLOW_WINDOW",
    "record_sloe_metrics",
    "get_sloe_metrics",
    "compute_fast_window",
    "compute_slow_window",
    "compute_error_budget_burn",
]
