"""Remaining rules for Tracer 12.

Rule types:
- new_entity: alert when a new key or model appears
- absence: alert when a collector's data goes stale, or a dormant key starts
  being used
- governance: alert when a key violates naming or ownership conventions
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Connection, text

logger = logging.getLogger(__name__)

# Number of days without usage before a key is considered dormant
DORMANT_DAYS = 30
# Number of days for a key naming convention check
NAMING_CHECK_DAYS = 30


def _now() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(UTC)


def _to_dt(ts: str | int) -> datetime:
    """Convert a timestamp (ISO string or Unix seconds) to a datetime."""
    if isinstance(ts, int):
        return datetime.fromtimestamp(ts, tz=UTC)
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(UTC)


def _lstamp(ts: datetime) -> str:
    """Convert a datetime to an ISO timestamp string."""
    return ts.isoformat()


def new_entity_rule(
    conn: Connection,
    snapshots: list[dict[str, Any]],
    interval_days: int = NAMING_CHECK_DAYS,
) -> list[dict[str, Any]]:
    """Check for new entities (keys or models) in the last interval_days.

    Returns a list of alert row dicts for any new entities found.
    """
    now = _now()
    cutoff = now - timedelta(days=interval_days)

    alerts = []

    # Find keys that appeared in the last interval_days
    for snapshot in snapshots:
        key_id = snapshot.get("api_key_id")
        provider = snapshot.get("provider")
        name = snapshot.get("name")
        snapshot_date = _to_dt(snapshot.get("snapshot_date", now))

        if snapshot_date >= cutoff and snapshot_date < now - timedelta(days=1):
            alerts.append(
                {
                    "fingerprint": f"new_entity.key.{provider}.{key_id}",
                    "rule_id": "new_entity",
                    "subject": key_id,
                    "severity": "info",
                    "state": "pending",
                    "first_fired_at": _lstamp(now),
                    "last_notified_at": None,
                    "resolved_at": None,
                    "fire_count": 1,
                    "message": (
                        f"New key '{name}' ({key_id}) appeared on {provider} "
                        f"at {snapshot_date.isoformat()}"
                    ),
                }
            )

    return alerts


def absence_rule(
    conn: Connection,
    provider: str,
    subject: str,
    subject_type: str = "key",
    days: int = DORMANT_DAYS,
) -> list[dict[str, Any]]:
    """Check for absence: collector staleness or dormant key.

    Returns a list of alert row dicts if the key has been dormant or the
    collector data is stale.
    """
    now = _now()
    cutoff = now - timedelta(days=days)

    alerts = []

    # Check for dormant key: key has no usage in the last N days
    rows = conn.execute(
        text(
            """
            SELECT MAX(bucket_start) as last_used
            FROM usage_fact
            WHERE provider = :provider
              AND api_key_id = :subject
              AND bucket_start >= :cutoff
            """
        ),
        {
            "provider": provider,
            "subject": subject,
            "cutoff": cutoff.isoformat(),
        },
    ).fetchone()

    last_used = rows.last_used if rows else None

    if last_used is None:
        # No usage found at all - key might be dormant
        alerts.append(
            {
                "fingerprint": f"absence.dormant.{provider}.{subject}",
                "rule_id": "absence",
                "subject": subject,
                "severity": "warning",
                "state": "pending",
                "first_fired_at": _lstamp(now),
                "last_notified_at": None,
                "resolved_at": None,
                "fire_count": 1,
                "message": (f"Key {subject} has no usage in the last {days} days"),
            }
        )

    return alerts


def governance_rule(
    conn: Connection,
    provider: str,
    naming_convention: str = r"^[a-z0-9_-]+$",
) -> list[dict[str, Any]]:
    """Check key names for governance violations.

    Returns a list of alert row dicts for keys that violate naming conventions.
    """
    now = _now()
    cutoff = now - timedelta(days=NAMING_CHECK_DAYS)

    alerts = []

    # Fetch inventory for the last interval_days
    rows = conn.execute(
        text(
            """
            SELECT api_key_id, name, status, owner, scope_id
            FROM key_inventory
            WHERE provider = :provider
              AND snapshot_date >= :cutoff
            """
        ),
        {"provider": provider, "cutoff": cutoff.isoformat()},
    ).fetchall()

    for row in rows:
        key_id = row.api_key_id
        name = row.name

        # Check for naming convention violations
        # (simple check: no uppercase letters, no special chars)
        if name and not all(c.islower() or c.isdigit() or c in "-_" for c in name):
            alerts.append(
                {
                    "fingerprint": f"governance.name.{provider}.{key_id}",
                    "rule_id": "governance",
                    "subject": key_id,
                    "severity": "warning",
                    "state": "pending",
                    "first_fired_at": _lstamp(now),
                    "last_notified_at": None,
                    "resolved_at": None,
                    "fire_count": 1,
                    "message": (
                        f"Key {key_id} has name '{name}' that violates "
                        f"naming convention (expected lowercase with hyphens/underscores)"
                    ),
                }
            )

    return alerts


def slo_burn_rule(
    conn: Connection,
    provider: str,
    threshold_pct: float = 5.0,
    window_days: int = 7,
) -> list[dict[str, Any]]:
    """Check SLO error-budget burn rate.

    Returns a list of alert row dicts if the SLO burn rate exceeds the
    threshold over the specified window.
    """
    now = _now()
    cutoff = now - timedelta(days=window_days)

    alerts = []

    # Fetch SLO metrics for the provider
    rows = conn.execute(
        text(
            """
            SELECT availability_pct, error_budget_burn_pct
            FROM sloe_metric
            WHERE provider = :provider
              AND start >= :cutoff
            ORDER BY start DESC
            """
        ),
        {
            "provider": provider,
            "cutoff": cutoff.isoformat(),
        },
    ).fetchall()

    if not rows:
        # No SLO data yet - can't evaluate
        return []

    # Compute the average availability over the window
    available_metrics = [r.availability_pct for r in rows if r.availability_pct is not None]

    if not available_metrics:
        # No data - unknown, don't alert
        return []

    avg_availability = sum(available_metrics) / len(available_metrics)
    avg_burn = sum(r.error_budget_burn_pct for r in rows if r.error_budget_burn_pct) / len(rows)

    if avg_burn >= threshold_pct:
        alerts.append(
            {
                "fingerprint": f"slo.burn.{provider}",
                "rule_id": "slo.burn",
                "subject": provider,
                "severity": "warning",
                "state": "pending",
                "first_fired_at": _lstamp(now),
                "last_notified_at": None,
                "resolved_at": None,
                "fire_count": 1,
                "message": (
                    f"SLO burn rate for {provider} is {avg_burn:.2f}% "
                    f"over the last {window_days} days "
                    f"(availability {avg_availability:.2f}%)"
                ),
            }
        )

    return alerts
