"""SLO tracking: availability windows, error-budget burn rate.

Adds an sloe_metric table to record provider availability over fast and slow
windows, plus error-budget burn rate so a slow degradation is caught before
an outage. No-data intervals are recorded as NULL availability (unknown),
never as 100%.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # sloe_metric: per-provider SLO availability over a fast window (1h) and a
    # slow window (24h), plus the error-budget burn rate.
    op.create_table(
        "sloe_metric",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("slo_name", sa.Text(), nullable=False),
        sa.Column("window", sa.Text(), nullable=False),
        sa.Column("start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("availability_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("error_budget_burn_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column(
            "captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("provider", "slo_name", "window", "start", "end"),
    )
    op.create_index(
        "ix_sloe_metric_provider_slo_name_window",
        "sloe_metric",
        ["provider", "slo_name", "window"],
    )
    op.create_index(
        "ix_sloe_metric_start_end", "sloe_metric", ["provider", "start", "end"]
    )


def downgrade() -> None:
    op.drop_index("ix_sloe_metric_start_end", "sloe_metric")
    op.drop_index("ix_sloe_metric_provider_slo_name_window", "sloe_metric")
    op.drop_table("sloe_metric")
