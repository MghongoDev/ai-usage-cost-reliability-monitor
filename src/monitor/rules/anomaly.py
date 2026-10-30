"""Usage-anomaly rule: robust_z-score detection on hourly buckets.

The robust_z-score uses the median and median absolute deviation (MAD) instead
of the mean and standard deviation. This means one past spike doesn't hide the
next. The rule evaluates on completed hourly buckets only, against the same
hour of week (e.g. all Mondays at 10:00), with a minimum-volume floor so a
quiet hour isn't flagged as an anomaly just because it has no traffic.

Threshold: a robust_z-score >= 3.5 (or configurable) on the subject's usage,
compared to the same hour of week over the recent history.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import Connection, text

logger = logging.getLogger(__name__)

# Robust Z-score threshold for anomaly detection
RULE_ANOMALY_THRESHOLD = 3.5
# Minimum volume (requests) before an hour bucket is evaluated
MIN_VOLUME_FLOOR = 10
# Number of previous weeks to include in the history
HISTORY_WEEKS = 4


def _subtract_dates(d: datetime, weeks: int) -> datetime:
    """Return a datetime shifted by the given number of weeks."""
    return d - timedelta(weeks=weeks)


def _is_same_hour_of_week(d1: datetime, d2: datetime) -> bool:
    """Return True if the two datetimes are the same hour of the same weekday."""
    return (
        d1.weekday() == d2.weekday()
        and d1.hour == d2.hour
        and d1.minute == d2.minute
    )


def _to_dt(ts: str | int) -> datetime:
    """Convert a timestamp (ISO string or Unix seconds) to a datetime."""
    if isinstance(ts, int):
        return datetime.fromtimestamp(ts, tz=UTC)
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(UTC)


def _get_hourly_buckets_for_week(
    conn: Connection,
    week_start: datetime,
    bucket_width: str = "1h",
) -> dict[datetime, int]:
    """Return a dict of {timestamp: total_requests} for each hourly bucket in a week.

    Only includes buckets with non-zero requests.
    """
    start = week_start.isoformat()
    end = (week_start + timedelta(days=7)).isoformat()

    rows = conn.execute(
        text(
            """
            SELECT bucket_start, SUM(requests) as total_requests
            FROM usage_fact
            WHERE provider = :provider
              AND bucket_start >= :start
              AND bucket_start < :end
              AND bucket_width = :bucket_width
            GROUP BY bucket_start
            ORDER BY bucket_start
            """
        ),
        {
            "provider": "anthropic",
            "start": start,
            "end": end,
            "bucket_width": bucket_width,
        },
    ).fetchall()

    result = {}
    for r in rows:
        dt = _to_dt(r.bucket_start)
        result[dt] = r.total_requests
    return result


def _robust_z_score(value: float, history: list[float]) -> float | None:
    """Compute the robust Z-score of a value against a history.

    robust_z = 0.6745 * (value - median) / MAD

    Returns None if MAD is zero (can't compute a meaningful score).
    """
    if not history:
        return None

    sorted_hist = sorted(history)
    median = sorted_hist[len(sorted_hist) // 2]

    if median == 0:
        return None

    mad = sorted(abs(v - median) for v in history)
    mad = mad[len(mad) // 2]

    if mad == 0:
        return None

    return 0.6745 * (value - median) / mad


def _find_same_hour_of_week(
    candidate: datetime, history: list[datetime]
) -> datetime | None:
    """Find a datetime in history matching the candidate's hour of week."""
    for h in history:
        if _is_same_hour_of_week(candidate, h):
            return h
    return None


def _current_hour_bucket(dt: datetime) -> datetime:
    """Return the start of the hour bucket for a datetime."""
    return dt.replace(minute=0, second=0, microsecond=0)


def detect_usage_anomalies(
    conn: Connection,
    window: tuple[str | int, str | int],
    provider: str = "anthropic",
    bucket_width: str = "1h",
    threshold: float = RULE_ANOMALY_THRESHOLD,
) -> list[dict]:
    """Run the usage-anomaly rule.

    Compares current usage on hourly buckets against the same hour of week
    over the last HISTORY_WEEKS weeks. Returns a list of alert row dicts for
    any bucket that exceeds the threshold.

    Arguments:
        conn: Database connection.
        window: (start, end) time range to evaluate.
        provider: Provider to detect anomalies for.
        bucket_width: Bucket width for usage (e.g., "1h").
        threshold: Robust Z-score threshold for flagging.

    Returns:
        List of alert row dicts.
    """
    now = datetime.now(UTC)
    start = _to_dt(window[0])
    end = _to_dt(window[1])

    alerts = []

    # Walk through each hour of the current window
    cursor = start
    hourly_width = timedelta(hours=1)

    while cursor < end:
        # Build history of the same hour of week
        history_dates = []
        for w in range(HISTORY_WEEKS + 1):
            h = cursor - timedelta(weeks=w)
            history_dates.append(h)

        # Fetch current hour usage
        current_start = _current_hour_bucket(cursor).isoformat()
        current_end = _current_hour_bucket(cursor + hourly_width).isoformat()

        current_rows = conn.execute(
            text(
                """
                SELECT SUM(requests) as total_requests
                FROM usage_fact
                WHERE provider = :provider
                  AND bucket_start >= :start
                  AND bucket_start < :end
                  AND bucket_width = :bucket_width
                """
            ),
            {
                "provider": provider,
                "start": current_start,
                "end": current_end,
                "bucket_width": bucket_width,
            },
        ).fetchone()

        current_total = current_rows.total_requests if current_rows else 0

        # Apply minimum volume floor
        if current_total < MIN_VOLUME_FLOOR:
            cursor += hourly_width
            continue

        # Fetch history usage for the same hour of week
        history_usage = []
        for h in history_dates:
            h_start = _current_hour_bucket(h).isoformat()
            h_end = _current_hour_bucket(h + hourly_width).isoformat()
            rows = conn.execute(
                text(
                    """
                    SELECT SUM(requests) as total_requests
                    FROM usage_fact
                    WHERE provider = :provider
                      AND bucket_start >= :h_start
                      AND bucket_start < :h_end
                      AND bucket_width = :bucket_width
                    """
                ),
                {
                    "provider": provider,
                    "h_start": h_start,
                    "h_end": h_end,
                    "bucket_width": bucket_width,
                },
            ).fetchone()
            if rows and rows.total_requests is not None:
                history_usage.append(float(rows.total_requests))

        # Check if current usage is an anomaly
        if history_usage:
            z_score = _robust_z_score(float(current_total), history_usage)
            if z_score is not None and z_score >= threshold:
                alerts.append(
                    {
                        "fingerprint": (
                            f"usage.anomaly.{provider}."
                            f"{current_start}"
                        ),
                        "rule_id": "usage.anomaly",
                        "subject": cursor.isoformat(),
                        "severity": "critical",
                        "state": "pending",
                        "first_fired_at": now.isoformat(),
                        "last_notified_at": None,
                        "resolved_at": None,
                        "fire_count": 1,
                        "message": (
                            f"Usage anomaly detected: "
                            f"robust_z={z_score:.2f}, "
                            f"current={current_total}, "
                            f"history_median={sorted(history_usage)[len(history_usage)//2]}"
                        ),
                    }
                )

        cursor += hourly_width

    return alerts
