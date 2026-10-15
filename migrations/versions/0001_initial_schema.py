"""initial schema: fact tables, inventory, pricing, budgets, probes, runs, alerts, raw payloads

Revision ID: 0001
Revises:
Create Date: 2026-10-14

Design notes:
- usage_fact's primary key is (provider, bucket_start, bucket_width, dims_key).
  dims_key is a generated column that collapses the three nullable dimensions
  (scope_id, api_key_id, model) into one string with '~' for nulls, so a row
  with no key attribution (console usage) or no scope (default workspace) still
  stores. See monitor/db/schema.py for the rule, which this column mirrors.
- cache_creation is a first-class token column because Phase 3 prices cache
  writes separately from cache reads.
- probe_result, collector_run, and raw_payload use identity primary keys: their
  natural keys (a probe at a moment) are either unstable or carry no uniqueness
  worth enforcing.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usage_fact",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bucket_width", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Text(), nullable=True),
        sa.Column("api_key_id", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("requests", sa.BigInteger(), nullable=True),
        sa.Column("input_uncached", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("input_cached", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cache_creation", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("extra", sa.dialects.postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "dims_key",
            sa.Text(),
            sa.Computed(
                "coalesce(scope_id, '~') || '|'"
                " || coalesce(api_key_id, '~') || '|'"
                " || coalesce(model, '~')",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("provider", "bucket_start", "bucket_width", "dims_key"),
    )

    op.create_table(
        "cost_fact",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("scope_id", sa.Text(), nullable=True),
        sa.Column("line_item", sa.Text(), nullable=False),
        sa.Column("amount_usd", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cost_type", sa.Text(), nullable=True),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # Same rule as usage_fact: a nullable dimension in the PK collapses to
        # the '~' marker via a generated column, so a null-scope cost row
        # (default workspace) still stores.
        sa.Column(
            "scope_key",
            sa.Text(),
            sa.Computed("coalesce(scope_id, '~')", persisted=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("provider", "day", "scope_key", "line_item"),
    )

    op.create_table(
        "key_inventory",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("api_key_id", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("owner", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra", sa.dialects.postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("provider", "snapshot_date", "api_key_id"),
    )

    op.create_table(
        "price_table",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("token_class", sa.Text(), nullable=False),
        sa.Column("usd_per_million", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("provider", "model", "token_class", "effective_from"),
    )

    op.create_table(
        "budget",
        sa.Column("scope_id", sa.Text(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("amount_usd", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.PrimaryKeyConstraint("scope_id", "month"),
    )

    op.create_table(
        "probe_result",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("probed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.BigInteger(), nullable=True),
        sa.Column("output_tokens", sa.BigInteger(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_probe_result_provider_probed_at", "probe_result", ["provider", "probed_at"])

    op.create_table(
        "collector_run",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rows_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_collector_run_source_started_at", "collector_run", ["source", "started_at"])

    op.create_table(
        "alert_event",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("first_fired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fire_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("message", sa.Text(), nullable=True),
    )
    op.create_index("ix_alert_event_fingerprint", "alert_event", ["fingerprint"], unique=True)
    op.create_index("ix_alert_event_state", "alert_event", ["state"])

    op.create_table(
        "raw_payload",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("params", sa.dialects.postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("body", sa.dialects.postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_raw_payload_fetched_at", "raw_payload", ["fetched_at"])


def downgrade() -> None:
    op.drop_table("raw_payload")
    op.drop_table("alert_event")
    op.drop_table("collector_run")
    op.drop_table("probe_result")
    op.drop_table("budget")
    op.drop_table("price_table")
    op.drop_table("key_inventory")
    op.drop_table("cost_fact")
    op.drop_table("usage_fact")
