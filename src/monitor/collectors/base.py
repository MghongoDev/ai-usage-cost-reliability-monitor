"""The UsageSource interface: one shape for every provider.

Adding a provider means implementing these three methods against its admin
API. The collector runner, scheduler, and idempotency logic are provider-agnostic.
"""

from typing import Any, Protocol


class UsageSource(Protocol):
    """Read-only access to one provider's usage, cost, and key inventory."""

    def fetch_usage(
        self, window: tuple[str | int, str | int], bucket_width: str
    ) -> tuple[list[dict[str, Any]], int]:
        """Return (usage rows, unknown field count) for [start, end) at the given bucket width.

        Rows are the dicts produced by the provider's normalize function.
        """
        ...

    def fetch_costs(self, window: tuple[str, str]) -> list[dict[str, Any]]:
        """Return cost rows for [start, end)."""
        ...

    def list_keys(self) -> list[dict[str, Any]]:
        """Return the key inventory for this provider."""
        ...
