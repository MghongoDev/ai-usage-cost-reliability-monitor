"""Test the Slack alerting sink.

Verifies that the Slack webhook is called with the correct payload when an
alert fires, including what happened, where, how much, since when, a dashboard
link, and a runbook link.
"""

from unittest.mock import patch

import httpx

from monitor.rules.alert import send_slack_alert


def _alert_row() -> dict:
    """Return a sample alert row dict."""
    return {
        "fingerprint": "budget.projection.scope_123.2026-11",
        "rule_id": "budget.projection",
        "subject": "scope_123",
        "severity": "warning",
        "state": "firing",
        "first_fired_at": "2026-11-01T12:00:00+00:00",
        "last_notified_at": None,
        "resolved_at": None,
        "fire_count": 1,
        "message": "Projected month-end spend $950.00 exceeds budget $1000.00 (95.0% of budget)",
    }


def test_send_slack_alert_posts_to_webhook() -> None:
    """A Slack alert posts a POST request to the webhook URL."""
    payload = {}

    def _fake_post(url: str, json: dict, headers: dict, timeout: int):
        payload.update(json)
        return httpx.Response(200, request=httpx.Request("POST", url))

    with patch("monitor.rules.alert.httpx.post", side_effect=_fake_post):
        send_slack_alert(
            webhook_url="https://hooks.slack.com/services/abc",
            alert=_alert_row(),
            dashboard_url="https://grafana.example.com/d/some-dashboard",
            runbook_url="https://runbooks.example.com/budget-projections",
        )

    assert payload["text"].startswith("*ALERT: budget.projection")
    assert "budget.projection" in payload["blocks"][0]["text"]["text"]
    assert "scope_123" in payload["blocks"][0]["text"]["text"]
    assert "2026-11-01T12:00:00+00:00" in payload["blocks"][0]["text"]["text"]
    dash_url = "<https://grafana.example.com/d/some-dashboard|Open Dashboard>"
    runbook_url = "<https://runbooks.example.com/budget-projections|View Runbook>"
    assert dash_url in payload["blocks"][0]["text"]["text"]
    assert runbook_url in payload["blocks"][0]["text"]["text"]


def test_send_slack_alert_logs_on_failure(caplog) -> None:
    """A failed Slack request is logged as a warning, not raised."""
    with patch("monitor.rules.alert.httpx.post", return_value=httpx.Response(500)):
        send_slack_alert(
            webhook_url="https://hooks.slack.com/services/abc",
            alert=_alert_row(),
            dashboard_url="https://grafana.example.com/d/some-dashboard",
            runbook_url="https://runbooks.example.com/budget-projections",
        )
        assert "Slack alert failed" in caplog.text
