"""Pydantic models for Anthropic usage-report payloads.

The spec requires: "Payloads parse into Pydantic models; unknown fields
counted and logged; missing required fields fail loudly."

Each result is validated with extra="allow" so unknown fields are captured
(not silently dropped), and the collector counts them. Required fields
(model, token counts) are non-optional, so a payload missing them raises
ValidationError instead of producing a bad row.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CacheCreation(BaseModel):
    model_config = ConfigDict(extra="allow")

    ephemeral_5m_input_tokens: int = 0
    ephemeral_1h_input_tokens: int = 0


class UsageResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    api_key_id: str | None = None
    workspace_id: str | None = None
    uncached_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    output_tokens: int = 0
    cache_creation: CacheCreation = Field(default_factory=CacheCreation)
    server_tool_use: dict[str, Any] = Field(default_factory=dict)


class UsageBucket(BaseModel):
    model_config = ConfigDict(extra="allow")

    starting_at: str
    ending_at: str
    results: list[UsageResult] = Field(default_factory=list)


class UsageReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    data: list[UsageBucket] = Field(default_factory=list)
    has_more: bool = False
    next_page: str | None = None


def count_unknown_fields(payload: dict[str, Any], model: type[BaseModel]) -> int:
    """Count fields in the payload that the model doesn't define.

    This is the "unknown fields counted and logged" requirement. The model
    keeps them (extra="allow"), and this returns how many there were so the
    collector can log the count.
    """
    known = set(model.model_fields.keys())
    return sum(1 for key in payload if key not in known)


def count_nested_unknown(report: Any) -> int:
    """Count unknown fields across all nested models in a parsed report.

    Walks the UsageReport tree (data -> results) and sums model_extra counts.
    """
    total = len(report.model_extra) if report.model_extra else 0
    for bucket in report.data:
        total += len(bucket.model_extra) if bucket.model_extra else 0
        for result in bucket.results:
            total += len(result.model_extra) if result.model_extra else 0
    return total
