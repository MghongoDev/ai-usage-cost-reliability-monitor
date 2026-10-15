"""Probe outcome classification and availability math.

The core acceptance criteria: every outcome is classified (ok, rate_limited,
server_error, overloaded, timeout, auth_error, bad_request, network), and
availability math treats no-data intervals as unknown, not 100%.
"""

from monitor.probes.classify import classify_outcome, compute_availability


class TestClassifyOutcome:
    def test_ok_for_2xx(self) -> None:
        assert classify_outcome(status_code=200, error=None) == "ok"

    def test_rate_limited_for_429(self) -> None:
        assert classify_outcome(status_code=429, error=None) == "rate_limited"

    def test_server_error_for_5xx(self) -> None:
        assert classify_outcome(status_code=500, error=None) == "server_error"
        assert classify_outcome(status_code=502, error=None) == "server_error"
        assert classify_outcome(status_code=503, error=None) == "server_error"

    def test_overloaded_for_529(self) -> None:
        assert classify_outcome(status_code=529, error=None) == "overloaded"

    def test_auth_error_for_401_403(self) -> None:
        assert classify_outcome(status_code=401, error=None) == "auth_error"
        assert classify_outcome(status_code=403, error=None) == "auth_error"

    def test_bad_request_for_400(self) -> None:
        assert classify_outcome(status_code=400, error=None) == "bad_request"

    def test_timeout_from_exception(self) -> None:
        assert classify_outcome(status_code=None, error="timeout") == "timeout"

    def test_network_from_exception(self) -> None:
        assert classify_outcome(status_code=None, error="connection") == "network"

    def test_error_takes_precedence_over_status(self) -> None:
        # A timeout error with a status code should still classify as timeout
        assert classify_outcome(status_code=200, error="timeout") == "timeout"


class TestComputeAvailability:
    def test_all_ok_is_100_percent(self) -> None:
        outcomes = ["ok", "ok", "ok"]
        assert compute_availability(outcomes) == 100.0

    def test_half_ok_is_50_percent(self) -> None:
        outcomes = ["ok", "server_error", "ok", "server_error"]
        assert compute_availability(outcomes) == 50.0

    def test_no_data_is_unknown_not_100(self) -> None:
        # The critical case: no probes in the interval must NOT look like 100% available
        assert compute_availability([]) is None

    def test_429_counts_as_not_ok(self) -> None:
        outcomes = ["ok", "rate_limited"]
        assert compute_availability(outcomes) == 50.0

    def test_timeout_counts_as_not_ok(self) -> None:
        outcomes = ["ok", "timeout"]
        assert compute_availability(outcomes) == 50.0
