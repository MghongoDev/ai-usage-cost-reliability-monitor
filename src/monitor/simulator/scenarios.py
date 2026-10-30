# Scenarios: labelled fault injections for the simulator.

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

# Default scenarios, keyed by name. These are the canonical scenarios used
# by the backtest harness.
DEFAULT_SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "runaway_loop",
        "start": "2026-10-01T12:00:00Z",
        "duration": "2h",
        "ground_truth": "usage_spike on apikey_01, 10x tokens for ~2 hours",
        "injectors": [
            {
                "type": "usage_spike",
                "scope": "apikey_01",
                "multiplier": 10.0,
                "start": "2026-10-01T12:00:00Z",
                "end": "2026-10-01T14:00:00Z",
            }
        ],
    },
    {
        "name": "new_model_emerges",
        "start": "2026-10-05T00:00:00Z",
        "duration": "1d",
        "ground_truth": "new model appears on an existing key",
        "injectors": [
            {
                "type": "new_entity",
                "entity_type": "model",
                "name": "claude-opus-6",
                "appearing_at": "2026-10-05T00:00:00Z",
            }
        ],
    },
    {
        "name": "slow_usage_drift",
        "start": "2026-10-08T00:00:00Z",
        "duration": "7d",
        "ground_truth": "usage drifts upward ~1.5x over two weeks",
        "injectors": [
            {
                "type": "usage_drift",
                "multiplier": 1.5,
                "start": "2026-10-08T00:00:00Z",
                "end": "2026-10-15T00:00:00Z",
            }
        ],
    },
    {
        "name": "provider_outage",
        "start": "2026-10-12T10:00:00Z",
        "duration": "3h",
        "ground_truth": "probe 5xx and timeouts for 3 hours",
        "injectors": [
            {
                "type": "probe_outage",
                "start": "2026-10-12T10:00:00Z",
                "end": "2026-10-12T13:00:00Z",
            }
        ],
    },
    {
        "name": "collector_outage",
        "start": "2026-10-14T00:00:00Z",
        "duration": "6h",
        "ground_truth": "collector stale data for 6 hours",
        "injectors": [
            {
                "type": "collector_outage",
                "start": "2026-10-14T00:00:00Z",
                "end": "2026-10-14T06:00:00Z",
            }
        ],
    },
    {
        "name": "dormant_key_wakes",
        "start": "2026-10-15T00:00:00Z",
        "duration": "6h",
        "ground_truth": "dormant key starts being used",
        "injectors": [
            {
                "type": "dormant_key_wake",
                "key": "apikey_04",
                "starts_using": "2026-10-15T00:00:00Z",
                "duration": "6h",
            }
        ],
    },
    {
        "name": "cache_hit_collapse",
        "start": "2026-10-18T00:00:00Z",
        "duration": "12h",
        "ground_truth": "cache-hit collapse after a prompt change",
        "injectors": [
            {
                "type": "cache_hit_collapse",
                "starts_at": "2026-10-18T00:00:00Z",
                "duration": "12h",
            }
        ],
    },
]


def all_scenarios() -> list[dict[str, Any]]:
    """Return the full list of scenarios."""
    return DEFAULT_SCENARIOS


def get_scenario(scenario_name: str) -> dict[str, Any] | None:
    """Look up a scenario by name."""
    for scenario in DEFAULT_SCENARIOS:
        if scenario["name"] == scenario_name:
            return scenario
    return None


def active_scenarios(now: str) -> list[dict[str, Any]]:
    """Return the scenarios active at the given time.

    Arguments:
        now: ISO 8601 timestamp string.
    """
    now_dt = datetime.fromisoformat(now.replace("Z", "+00:00")).astimezone(UTC)
    active = []
    for scenario in DEFAULT_SCENARIOS:
        start_dt = datetime.fromisoformat(
            scenario["start"].replace("Z", "+00:00")
        ).astimezone(UTC)
        end_dt = start_dt + duration_to_timedelta(scenario.get("duration", "1h"))
        if start_dt <= now_dt < end_dt:
            active.append(scenario)
    return active


def duration_to_timedelta(duration: str) -> timedelta:
    """Parse a duration string like '2h', '3d', '15m' into a timedelta."""
    match = re.match(r"(\d+)([smhd])", duration)
    if not match:
        raise ValueError(f"Invalid duration: {duration}")
    value = int(match.group(1))
    unit = match.group(2)
    if unit == "s":
        return timedelta(seconds=value)
    if unit == "m":
        return timedelta(minutes=value)
    if unit == "h":
        return timedelta(hours=value)
    if unit == "d":
        return timedelta(days=value)
    raise ValueError(f"Unknown unit: {unit}")
