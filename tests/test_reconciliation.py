"""Reconciliation: estimated vs billed cost per scope per day.

The core acceptance criterion: reconciliation compares estimated against
billed cost per scope per day with a recon_error_pct metric. Residuals are
expected from batch discounts, priority-tier gaps, code execution, and
rounding — they're investigated, not hidden.
"""

import pytest
from sqlalchemy import create_engine, text

from monitor.config import settings
from monitor.db.upsert import budget_projection_query, reconciliation_query


@pytest.fixture()
def db():
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE usage_fact, cost_fact, key_inventory,"
                " price_table, budget, collector_run, raw_payload"
            )
        )
    yield engine
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE usage_fact, cost_fact, key_inventory,"
                " price_table, budget, collector_run, raw_payload"
            )
        )
    engine.dispose()


class TestReconciliationQuery:
    def test_estimated_and_billed_per_scope_per_day(self, db) -> None:
        # Seed usage, prices, and cost_fact
        from monitor.collectors.cost import seed_price_table
        from monitor.db.upsert import upsert_cost_rows, upsert_usage_rows

        with db.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO price_table (provider, model, token_class,"
                    " usd_per_million, effective_from)"
                    " VALUES (:provider, :model, :token_class, :usd_per_million,"
                    " :effective_from)"
                ),
                seed_price_table(),
            )
            upsert_usage_rows(
                conn,
                [
                    {
                        "provider": "anthropic",
                        "bucket_start": "2026-10-14T10:00:00Z",
                        "bucket_width": "1h",
                        "scope_id": "wrkspc_01",
                        "api_key_id": "apikey_01",
                        "model": "claude-opus-5-5",
                        "requests": 5,
                        "input_uncached": 1000,
                        "input_cached": 0,
                        "cache_creation": 0,
                        "output_tokens": 500,
                        "extra": "{}",
                    }
                ],
            )
            upsert_cost_rows(
                conn,
                [
                    {
                        "provider": "anthropic",
                        "day": "2026-10-14",
                        "scope_id": "wrkspc_01",
                        "line_item": "Claude Opus 5.5 Usage",
                        "amount_usd": 0.0412,
                        "description": "Claude Opus 5.5 Usage",
                        "cost_type": "tokens",
                    }
                ],
            )
            rows = reconciliation_query(conn)

        assert len(rows) == 1
        row = rows[0]
        assert row.provider == "anthropic"
        assert row.scope_id == "wrkspc_01"
        assert str(row.day) == "2026-10-14"
        # Estimated: 1000 * $4/M + 500 * $20/M = $0.004 + $0.010 = $0.014
        assert float(row.estimated_usd) == pytest.approx(0.014, rel=1e-3)
        assert float(row.billed_usd) == pytest.approx(0.0412, rel=1e-3)
        # recon_error_pct = |estimated - billed| / billed * 100
        expected_pct = abs(0.014 - 0.0412) / 0.0412 * 100
        assert float(row.recon_error_pct) == pytest.approx(expected_pct, rel=1e-2)


class TestBudgetProjection:
    def test_mtd_and_projected_spend(self, db) -> None:
        from monitor.db.upsert import upsert_budget_rows, upsert_cost_rows

        with db.begin() as conn:
            upsert_budget_rows(
                conn,
                [{"scope_id": "wrkspc_01", "month": "2026-10-01", "amount_usd": 100.00}],
            )
            upsert_cost_rows(
                conn,
                [
                    {
                        "provider": "anthropic",
                        "day": "2026-10-14",
                        "scope_id": "wrkspc_01",
                        "line_item": "Usage",
                        "amount_usd": 10.00,
                        "description": "Usage",
                        "cost_type": "tokens",
                    },
                    {
                        "provider": "anthropic",
                        "day": "2026-10-14",
                        "scope_id": "wrkspc_02",
                        "line_item": "Usage",
                        "amount_usd": 5.00,
                        "description": "Usage",
                        "cost_type": "tokens",
                    },
                ],
            )
            rows = budget_projection_query(conn, month="2026-10-01")

        wrkspc_01 = [r for r in rows if r.scope_id == "wrkspc_01"]
        assert len(wrkspc_01) == 1
        row = wrkspc_01[0]
        assert row.mtd_usd == pytest.approx(10.00, rel=1e-3)
        assert row.budget_usd == pytest.approx(100.00, rel=1e-3)
        # 14 days into a 31-day month, $10 spent -> projected ~$22
        assert row.projected_usd > row.mtd_usd
        assert row.projected_usd < row.budget_usd * 2

    def test_percent_of_budget(self, db) -> None:
        from monitor.db.upsert import upsert_budget_rows, upsert_cost_rows

        with db.begin() as conn:
            upsert_budget_rows(
                conn,
                [{"scope_id": "wrkspc_01", "month": "2026-10-01", "amount_usd": 100.00}],
            )
            upsert_cost_rows(
                conn,
                [
                    {
                        "provider": "anthropic",
                        "day": "2026-10-14",
                        "scope_id": "wrkspc_01",
                        "line_item": "Usage",
                        "amount_usd": 50.00,
                        "description": "Usage",
                        "cost_type": "tokens",
                    }
                ],
            )
            rows = budget_projection_query(conn, month="2026-10-01")

        row = [r for r in rows if r.scope_id == "wrkspc_01"][0]
        assert row.pct_of_budget == pytest.approx(50.0, rel=1e-2)
