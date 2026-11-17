"""Phase 2 tests: governed metrics are correct, reconcile, and the DQ suite catches faults."""
import datetime as dt
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from nodi.metrics import REF, Metrics, MetricNotAvailable
from nodi.warehouse.build import connect
from nodi.warehouse.dq import run_dq
from nodi.warehouse.faults import FAULTS, run_fault_injection


@pytest.fixture(scope="module")
def m(wh):
    con = connect(wh)
    yield Metrics(con)
    con.close()


def raw(cfg):
    return Path(cfg["paths"]["raw"]).as_posix()


def test_every_metric_is_fully_documented(m):
    cat = m.catalog()
    assert cat.metric.is_unique
    assert (cat.definition.str.len() > 30).all()
    for name in m.defs:
        if m.defs[name].get("type", "aggregate") == "aggregate":
            assert not REF.search(m.expression(name)), name


def test_every_available_metric_executes(m):
    for name, d in m.defs.items():
        if not m.available(name):  # model produced by a later phase (may run earlier in the session)
            assert d.get("available_from")
            with pytest.raises(MetricNotAvailable):
                m.get(name)
            continue
        by = [] if d.get("type") == "experiment_lift" else ["month_start"]
        df = m.get(name, by=by)
        assert len(df) > 0 and df[name].notna().any(), name


def test_headline_arpu_matches_independent_calculation(m, wh):
    month = dt.date(2025, 9, 1)
    got = m.get("arpu", where=f"month_start = DATE '{month}'")["arpu"].iloc[0]
    r = duckdb.sql(f"""SELECT SUM(amount_bdt) g, COUNT(DISTINCT sub_id) n
                       FROM read_parquet('{raw(wh)}/recharges/*/*.parquet')
                       WHERE date_trunc('month', recharge_date) = DATE '{month}'""").df()
    expected = r.g[0] * wh["economics"]["net_revenue_ratio"] / r.n[0]
    assert got == pytest.approx(expected, rel=1e-9)


def test_active_base_matches_independent_calculation(m, wh):
    """Recompute 'revenue event in prior 90 days' straight from raw files."""
    month = dt.date(2026, 2, 1)
    got = m.get("active_base", where=f"month_start = DATE '{month}'")["active_base"].iloc[0]
    exp = duckdb.sql(f"""
        WITH ev AS (
            SELECT sub_id, recharge_date d FROM read_parquet('{raw(wh)}/recharges/*/*.parquet')
            UNION ALL SELECT sub_id, activation_date FROM read_parquet('{raw(wh)}/subscribers.parquet')
                WHERE activation_date >= DATE '2025-01-01'
            UNION ALL SELECT sub_id, last_revenue_date_pre_window FROM read_parquet('{raw(wh)}/subscribers.parquet'))
        SELECT COUNT(DISTINCT sub_id) FROM ev
        WHERE d < DATE '{month}' AND d >= DATE '{month}' - INTERVAL 90 DAY""").fetchall()[0][0]
    assert got == exp


def test_churn_rate_matches_spells(m, wh):
    month = dt.date(2025, 11, 1)
    k = m.many(["churners", "active_base", "churn_rate"], where=f"month_start = DATE '{month}'")
    spells = pd.read_parquet(Path(wh["paths"]["raw"]) / "inactivity_spells.parquet")
    n = sum(1 for c in spells.churn_date.dropna() if c.year == 2025 and c.month == 11)
    assert k.churners.iloc[0] == n
    assert k.churn_rate.iloc[0] == pytest.approx(n / k.active_base.iloc[0])


def test_experiment_lift_matches_manual(m, wh):
    con = connect(wh)
    df = con.execute("SELECT arm, net_revenue_90d FROM mart_pilot_outcome").df()
    con.close()
    means, n = df.groupby("arm").net_revenue_90d.mean(), df.groupby("arm").size()
    got = m.get("incremental_revenue", by=[]).set_index("arm").incremental_revenue
    for arm in got.index:
        assert got[arm] == pytest.approx((means[arm] - means["control"]) * n[arm])


def test_slicing_reconciles_to_total(m):
    total = m.get("net_revenue")["net_revenue"].sum()
    by_div = m.get("net_revenue", by=["month_start", "division"])["net_revenue"].sum()
    assert by_div == pytest.approx(total)


def test_dq_suite_passes_on_clean_data(wh):
    con = connect(wh)
    df = run_dq(con, wh)
    con.close()
    assert (df.status != "FAIL").all(), df[df.status == "FAIL"]


def test_every_planted_fault_is_caught(wh):
    res = run_fault_injection(wh)
    assert len(res) == len(FAULTS)
    assert res.caught.all(), res[~res.caught]
