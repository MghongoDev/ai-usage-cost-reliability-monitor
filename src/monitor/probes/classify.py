"""Probe outcome classification and availability math.

Every probe outcome is classified into one of: ok, rate_limited, server_error,
overloaded, timeout, auth_error, bad_request, network. Availability is the
percentage of ok outcomes; no-data intervals return None (unknown), never 100%.
"""


def classify_outcome(status_code: int | None, error: str | None) -> str:
    """Classify a probe outcome from its status code or exception type."""
    if error:
        error_lower = error.lower()
        if "timeout" in error_lower:
            return "timeout"
        if "connection" in error_lower or "network" in error_lower:
            return "network"
        return "network"

    if status_code is None:
        return "network"

    if 200 <= status_code < 300:
        return "ok"
    if status_code == 429:
        return "rate_limited"
    if status_code == 529:
        return "overloaded"
    if status_code in (401, 403):
        return "auth_error"
    if status_code == 400:
        return "bad_request"
    if 500 <= status_code < 600:
        return "server_error"
    return "bad_request"


def compute_availability(outcomes: list[str]) -> float | None:
    """Compute availability as the percentage of ok outcomes.

    Returns None for no-data intervals (unknown), never 100%.
    """
    if not outcomes:
        return None
    ok_count = sum(1 for o in outcomes if o == "ok")
    return ok_count / len(outcomes) * 100.0
