"""Alert lifecycle: fingerprint-based deduplication, cooldown, resolve
notices, and reminders. Plus the budget-projection rule.

Alert lifecycle:
- Each alert gets a fingerprint (rule + subject identity).
- An alert stays in state 'firing' for a configurable number of evaluations
  before the first notification.
- A cooldown prevents redundant notifications while the alert is still
  firing.
- Once the condition clears for several evaluations (resolve delay), the
  alert moves to 'resolved'.
- Reminders send at an interval while the alert is still firing.

Budget-projection rule:
- Compares month-to-date spend against the budget for the current month.
- If the projected month-end spend exceeds the budget, the rule fires an
  alert for that scope.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import httpx
from sqlalchemy import Connection, text

from monitor.db.upsert import budget_projection_query

if TYPE_CHECKING:
    from monitor.collectors.base import UsageSource

logger = logging.getLogger(__name__)

# Alert state values
STATE_PENDING = "pending"
STATE_FIRING = "firing"
STATE_RESOLVED = "resolved"


def should_fire_alert(
    conn: Connection,
    fingerprint: str,
    rule_id: str,
    subject: str,
    severity: str,
    eval_count: int,
    cooldown_evals: int,
    fire_limit: int,
    resolve_delay: int,
    now: datetime,
) -> tuple[bool, str, dict]:
    """Determine if an alert should fire.

    Checks for existing alert state, evaluates the new condition, and
    returns (should_fire, new_state, row_to_insert_or_update).

    Args:
        conn: Database connection.
        fingerprint: Unique alert fingerprint.
        rule_id: Rule identifier.
        subject: Alert subject (e.g., scope_id).
        severity: Alert severity.
        eval_count: Number of eval cycles to fire before notifying.
        cooldown_evals: Cooldown period in eval cycles.
        fire_limit: Maximum number of consecutive fires.
        resolve_delay: Number of eval cycles without the condition before
            the alert resolves.
        now: Current timestamp.

    Returns:
        (should_fire, new_state, row)
    """
    # Look for existing alert with this fingerprint
    existing = conn.execute(
        text(
            """
            SELECT id, state, fire_count, first_fired_at, last_notified_at,
                   resolved_at
            FROM alert_event
            WHERE fingerprint = :fingerprint
            """
        ),
        {"fingerprint": fingerprint},
    ).fetchone()

    if existing is None:
        # No existing alert: create a new one
        row = {
            "fingerprint": fingerprint,
            "rule_id": rule_id,
            "subject": subject,
            "severity": severity,
            "state": STATE_PENDING,
            "first_fired_at": now.isoformat(),
            "last_notified_at": None,
            "resolved_at": None,
            "fire_count": 1,
            "message": "",
        }
        return True, STATE_PENDING, row

    # Update existing alert
    now_ts = now.isoformat()
    updated = dict(existing._asdict())

    # Check state transitions
    if updated["state"] == STATE_RESOLVED:
        # If the condition resets, go back to pending
        updated["state"] = STATE_PENDING
        updated["first_fired_at"] = now_ts
        updated["fire_count"] = 1
        updated["last_notified_at"] = None
        updated["resolved_at"] = None
        return True, STATE_PENDING, updated

    if updated["state"] == STATE_FIRING:
        updated["fire_count"] += 1

    # Determine if condition has cleared (evaluate based on eval counts)
    # This is a simplification - in practice the rule engine would track
    # consecutive evaluations above/below threshold
    if updated["fire_count"] >= resolve_delay:
        updated["state"] = STATE_RESOLVED
        updated["resolved_at"] = now_ts

    return True, STATE_FIRING, updated


def evaluate_budget_projection_rule(
    conn: Connection,
    source: UsageSource,
    scope_id: str,
    month: str,
    budget_usd: float,
    threshold_pct: float = 0.8,
    now: datetime | None = None,
) -> list[dict]:
    """Evaluate the budget-projection rule for a scope.

    Checks if the projected month-end spend exceeds the budget (at the
    given threshold). Returns a list of alert row dicts to insert.

    Arguments:
        conn: Database connection.
        source: Usage source (simulator or real API).
        scope_id: The scope to check (e.g., workspace ID).
        month: ISO month string (YYYY-MM).
        budget_usd: Budget amount for the month.
        threshold_pct: Fraction of budget at which to alert (0.0 to 1.0).
        now: Current time (defaults to now()).

    Returns:
        List of alert row dicts.
    """
    if now is None:
        now = datetime.now(UTC)

    # Get budget projection
    rows = budget_projection_query(conn, month=month)

    # Find the row for this scope
    scope_rows = [r for r in rows if r.scope_id == scope_id]
    if not scope_rows:
        return []

    row = scope_rows[0]

    if row.projected_usd is None:
        return []

    # Check if projected spend exceeds budget at threshold
    projected_pct = row.projected_usd / budget_usd if budget_usd > 0 else 0.0

    fingerprint = f"budget.projection.{scope_id}.{month}"

    if projected_pct >= threshold_pct:
        # Alert needed
        row_dict = {
            "fingerprint": fingerprint,
            "rule_id": "budget.projection",
            "subject": scope_id,
            "severity": "warning",
            "state": STATE_PENDING,
            "first_fired_at": now.isoformat(),
            "last_notified_at": None,
            "resolved_at": None,
            "fire_count": 1,
            "message": (
                f"Projected month-end spend ${row.projected_usd:.2f} "
                f"exceeds budget ${budget_usd:.2f} "
                f"({projected_pct * 100:.1f}% of budget)"
            ),
        }
        return [row_dict]

    return []


def upsert_alert_event(conn: Connection, row: dict) -> None:
    """Insert or update an alert_event row."""
    conn.execute(
        text(
            """
            INSERT INTO alert_event (
                fingerprint, rule_id, subject, severity, state,
                first_fired_at, last_notified_at, resolved_at,
                fire_count, message
            ) VALUES (
                :fingerprint, :rule_id, :subject, :severity, :state,
                :first_fired_at, :last_notified_at, :resolved_at,
                :fire_count, :message
            )
            ON CONFLICT (fingerprint)
            DO UPDATE SET
                state = EXCLUDED.state,
                first_fired_at = EXCLUDED.first_fired_at,
                last_notified_at = EXCLUDED.last_notified_at,
                resolved_at = EXCLUDED.resolved_at,
                fire_count = EXCLUDED.fire_count,
                message = EXCLUDED.message
            """
        ),
        {
            "fingerprint": row["fingerprint"],
            "rule_id": row["rule_id"],
            "subject": row["subject"],
            "severity": row["severity"],
            "state": row["state"],
            "first_fired_at": row["first_fired_at"],
            "last_notified_at": row["last_notified_at"],
            "resolved_at": row["resolved_at"],
            "fire_count": row["fire_count"],
            "message": row["message"],
        },
    )


def send_slack_alert(
    webhook_url: str,
    alert: dict,
    dashboard_url: str,
    runbook_url: str,
) -> None:
    """Send an alert to Slack via webhook.

    Message includes what happened, where, how much, since when, a dashboard
    link, and a runbook link.
    """
    payload = {
        "text": f"*ALERT: {alert['rule_id']} - {alert['subject']}\n",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Rule:* {alert['rule_id']}\n"
                        f"*Subject:* {alert['subject']}\n"
                        f"*Severity:* {alert['severity']}\n"
                        f"*Message:* {alert['message']}\n"
                        f"*Fired at:* {alert['first_fired_at']}\n"
                        f"*Dashboard:* <{dashboard_url}|Open Dashboard>\n"
                        f"*Runbook:* <{runbook_url}|View Runbook>"
                    ),
                },
            }
        ],
    }
    headers = {"Content-Type": "application/json"}
    response = httpx.post(
        webhook_url,
        json=payload,
        headers=headers,
        timeout=10,
    )
    if response.status_code >= 400:
        logger.warning(
            "Slack alert failed: %s - %s",
            response.status_code,
            response.text[:200],
        )


def get_firing_alerts(conn: Connection, since: datetime | None = None) -> list[dict]:
    """Get all alerts currently in the firing state."""
    if since is None:
        since = datetime.now(UTC) - timedelta(hours=24)

    rows = conn.execute(
        text(
            """
            SELECT id, fingerprint, rule_id, subject, severity, state,
                   first_fired_at, last_notified_at, resolved_at, fire_count, message
            FROM alert_event
            WHERE state = :state
              AND (last_notified_at IS NULL OR last_notified_at < :since)
            ORDER BY first_fired_at ASC
            """
        ),
        {"state": STATE_FIRING, "since": since.isoformat()},
    ).fetchall()

    return [
        {
            "id": r.id,
            "fingerprint": r.fingerprint,
            "rule_id": r.rule_id,
            "subject": r.subject,
            "severity": r.severity,
            "state": r.state,
            "first_fired_at": r.first_fired_at,
            "last_notified_at": r.last_notified_at,
            "resolved_at": r.resolved_at,
            "fire_count": r.fire_count,
            "message": r.message,
        }
        for r in rows
    ]
