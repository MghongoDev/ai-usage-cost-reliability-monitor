"""SLO tracking: per-provider availability over fast and slow windows, with
error-budget burn rate. Used to catch slow degradation before an outage.

Availability: percentage of probe outcomes that are 'ok'.
No-data intervals: availability is NULL (unknown), never 0 or 100%.
Error-budget burn: proportion of the monthly error budget already spent,
based on the slow-window (24h) availability.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Connection, text

logger = logging.getLogger(__name__)

# Outcome types for internal use (only referenced in type hints)
OutcomeType = str

# Fast window: 1 hour
FAST_WINDOW = "1h"
# Slow window: 24 hours
SLOW_WINDOW = "24h"
# SLO name for availability
AVAILABILITY_SLO = "availability"


def compute_availability_percent(outcomes: list[str]) -> float | None:
    """Compute availability as the percentage of 'ok' outcomes.

    Returns None for no-data intervals (unknown), never 0.
    """
    if not outcomes:
        return None
    ok_count = sum(1 for o in outcomes if o == "ok")
    return (ok_count / len(outcomes)) * 100.0


def classify_outcome(outcome: str) -> bool:
    """True if outcome is 'ok', False otherwise."""
    return outcome == "ok"


def compute_fast_window() -> timedelta:
    """Return the time delta for the fast window (1 hour)."""
    return timedelta(hours=1)


def compute_slow_window() -> timedelta:
    """Return the time delta for the slow window (24 hours)."""
    return timedelta(hours=24)


def compute_error_budget_burn(total_budget_pct: float, remaining_budget_pct: float) -> float:
    """Compute the proportion of the monthly error budget already spent.

    Args:
        total_budget_pct: The monthly error budget as a percentage
            (e.g., 1% = 1.0).
        remaining_budget_pct: The remaining error budget as a percentage.

    Returns:
        Burned budget as a percentage (0.0 to total_budget_pct).
    """
    if total_budget_pct == 0:
        return 0.0
    spent = total_budget_pct - remaining_budget_pct
    return max(0.0, min(spent, total_budget_pct))


def record_sloe_metrics(
    conn: Connection,
    provider: str,
    now: datetime,
    outcomes: list[str],
) -> None:
    """Record SLO metrics for a provider.

    Records availability for both the fast (1h) and slow (24h) windows,
    plus the error-budget burn for the availability SLO.
    """
    fast_start = now - compute_fast_window()
    slow_start = now - compute_slow_window()

    # Fast window availability
    fast_outcomes = [o for o in outcomes if FAST_WINDOW_START(o, now)]
    fast_availability = compute_availability_percent(fast_outcomes)

    # Slow window availability
    slow_outcomes = [o for o in outcomes if SLOW_WINDOW_START(o, now)]
    slow_availability = compute_availability_percent(slow_outcomes)

    # Error-budget burn: assume a monthly error budget of 1% for the
    # availability SLO. Remaining budget is computed from slow-window
    # availability.
    burn_pct = max(0.0, 100.0 - slow_availability) if slow_availability is not None else None

    _store_sloe_metrics(
        conn,
        provider,
        AVAILABILITY_SLO,
        FAST_WINDOW,
        fast_start,
        now,
        fast_availability,
        burn_pct,
    )
    _store_sloe_metrics(
        conn,
        provider,
        AVAILABILITY_SLO,
        SLOW_WINDOW,
        slow_start,
        now,
        slow_availability,
        burn_pct,
    )


def _store_sloe_metrics(
    conn: Connection,
    provider: str,
    slo_name: str,
    window: str,
    start: datetime,
    end: datetime,
    availability_pct: float | None,
    error_budget_burn_pct: float | None,
) -> None:
    """Insert or update a sloe_metric row."""
    conn.execute(
        text(
            """
            INSERT INTO sloe_metric (
                provider, slo_name, window, start, end,
                availability_pct, error_budget_burn_pct
            ) VALUES (
                :provider, :slo_name, :window, :start, :end,
                :availability_pct, :error_budget_burn_pct
            )
            ON CONFLICT (provider, slo_name, window, start, end)
            DO UPDATE SET
                availability_pct = EXCLUDED.availability_pct,
                error_budget_burn_pct = EXCLUDED.error_budget_burn_pct,
                captured_at = now()
            """
        ),
        {
            "provider": provider,
            "slo_name": slo_name,
            "window": window,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "availability_pct": availability_pct,
            "error_budget_burn_pct": error_budget_burn_pct,
        },
    )


def FAST_WINDOW_START(outcome_time: str, now: datetime) -> bool:
    """Check if a probe outcome falls within the fast window (1 hour)."""
    try:
        t = datetime.fromisoformat(outcome_time.replace("Z", "+00:00"))
        return t >= now - compute_fast_window()
    except (ValueError, TypeError):
        return False


def SLOW_WINDOW_START(outcome_time: str, now: datetime) -> bool:
    """Check if a probe outcome falls within the slow window (24 hours)."""
    try:
        t = datetime.fromisoformat(outcome_time.replace("Z", "+00:00"))
        return t >= now - compute_slow_window()
    except (ValueError, TypeError):
        return False


def get_sloe_metrics(
    conn: Connection, provider: str, slo_name: str = AVAILABILITY_SLO
) -> list[dict[str, Any]]:
    """Fetch SLO metrics for a provider, most recent first."""
    rows = conn.execute(
        text(
            """
            SELECT window, start, end, availability_pct,
                   error_budget_burn_pct
            FROM sloe_metric
            WHERE provider = :provider
              AND slo_name = :slo_name
            ORDER BY start DESC
            """
        ),
        {"provider": provider, "slo_name": slo_name},
    ).fetchall()

    return [
        {
            "window": r.window,
            "start": r.start.isoformat() if r.start else None,
            "end": r.end.isoformat() if r.end else None,
            "availability_pct": r.availability_pct,
            "error_budget_burn_pct": r.error_budget_burn_pct,
        }
        for r in rows
    ]


def availability_below_threshold(metrics: list[dict[str, Any]], threshold_pct: float) -> bool:
    """Check if any recent SLO metric is below the threshold."""
    if not metrics:
        return True  # No data: treat as below threshold (unknown is bad)
    for m in metrics:
        if m["availability_pct"] is not None:
            return bool(m["availability_pct"] < threshold_pct)
    return False
