"""Shared constants for the Anthropic collector and simulator."""

# Per-bucket-width window caps, mirroring the real API's documented limits.
BUCKET_LIMITS: dict[str, int] = {
    "1m": 1440,  # 24h
    "1h": 168,   # 7 days
    "1d": 31,    # 31 days
}

VERSION = "2023-06-01"
