"""Phase 1 tests: reproducibility, internal consistency, planted behaviours, truth firewall."""
import hashlib
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from nodi.config import ROOT
from nodi.simulate import catalog as C
from nodi.simulate.calendar import build_calendar
from nodi.simulate.run import simulate

from conftest import N_TEST, small_cfg


def q(sql: str) -> pd.DataFrame:
    return duckdb.sql(sql).df()


def raw(cfg) -> str:
    return Path(cfg["paths"]["raw"]).as_posix()


def truth(cfg) -> str:
    return Path(cfg["paths"]["truth"]).as_posix()


def _digest(cfg) -> str:
    df = q(f"SELECT * FROM read_parquet('{raw(cfg)}/recharges/*/*.parquet') ORDER BY ALL")
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=False).values.tobytes()).hexdigest()


def test_reproducible_with_fixed_seed(sim, tmp_path):
    cfg2 = small_cfg(tmp_path)
    simulate(cfg2)
    assert _digest(sim) == _digest(cfg2)


def test_no_revenue_after_true_churn(sim):
    bad = q(f"""
        SELECT COUNT(*) n FROM read_parquet('{raw(sim)}/recharges/*/*.parquet') r
        JOIN read_parquet('{truth(sim)}/subscriber_truth.parquet') t USING (sub_id)
        WHERE t.true_churn_date IS NOT NULL AND r.recharge_date >= t.true_churn_date""")
    assert bad.n[0] == 0


def test_no_events_before_activation(sim):
    bad = q(f"""
        SELECT COUNT(*) n FROM read_parquet('{raw(sim)}/recharges/*/*.parquet') r
        JOIN read_parquet('{raw(sim)}/subscribers.parquet') s USING (sub_id)
        WHERE r.recharge_date < s.activation_date""")
    assert bad.n[0] == 0


def test_amounts_are_denominations_or_pack_prices(sim):
    amts = set(q(f"SELECT DISTINCT amount_bdt a FROM read_parquet('{raw(sim)}/recharges/*/*.parquet')").a)
    allowed = set(C.DENOMINATIONS.tolist()) | set(C.PACK_PRICE.tolist())
    assert amts <= allowed


def test_feature_phones_use_no_data(sim):
    mb = q(f"""
        SELECT SUM(data_mb) mb FROM read_parquet('{raw(sim)}/daily_usage/*/*.parquet') u
        JOIN read_parquet('{raw(sim)}/subscribers.parquet') s USING (sub_id)
        WHERE s.handset_tier = 'feature_phone'""")
    assert (mb.mb[0] or 0) == 0


def test_eid_ul_fitr_recharge_spike(sim):
    cal = build_calendar(sim)
    eid = cal.date(cal.day_of("2025-03-31"))
    df = q(f"""SELECT recharge_date d, COUNT(*) n FROM read_parquet('{raw(sim)}/recharges/*/*.parquet')
               GROUP BY 1""")
    df["d"] = pd.to_datetime(df.d).dt.date
    s = df.set_index("d").n
    pre = s[[eid - pd.Timedelta(days=k) for k in range(1, 4)]].mean()
    base = s[[eid - pd.Timedelta(days=k) for k in range(15, 43)]].mean()
    assert pre > 1.4 * base


def test_pilot_is_randomised_and_balanced(sim):
    df = q(f"""
        WITH p AS (SELECT sub_id, offer_id FROM read_parquet('{raw(sim)}/offer_exposures.parquet')
                   WHERE campaign_type = 'pilot'),
        pre AS (SELECT sub_id, COUNT(*) n FROM read_parquet('{raw(sim)}/recharges/*/*.parquet')
                WHERE recharge_date < DATE '2026-01-01' GROUP BY 1)
        SELECT p.offer_id, AVG(COALESCE(pre.n, 0)) m, COUNT(*) k FROM p LEFT JOIN pre USING (sub_id)
        GROUP BY 1""")
    assert len(df) == 5
    assert df.k.max() - df.k.min() <= 1
    assert df.m.max() / df.m.min() < 1.15  # no arm systematically more active pre-pilot


def test_inactivity_spells_consistent(sim):
    df = pd.read_parquet(Path(sim["paths"]["raw"]) / "inactivity_spells.parquet")
    assert (df.silent_days >= sim["churn"]["dormant_days"]).all()
    assert (df.reached_churn == (df.silent_days >= sim["churn"]["churn_days"])).all()
    assert df.loc[df.reactivated, "return_date"].notna().all()


def test_planted_truth_has_all_response_groups(sim):
    g = q(f"SELECT DISTINCT response_group g FROM read_parquet('{truth(sim)}/treatment_truth.parquet')").g
    assert {"persuadable", "sure_thing", "lost_cause", "sleeping_dog"} <= set(g)


def test_truth_effects_are_heterogeneous(sim):
    df = pd.read_parquet(Path(sim["paths"]["truth"]) / "treatment_truth.parquet")
    for o, grp in df.groupby("offer_id"):
        assert (grp.true_log_hazard_effect < 0).mean() > 0.3, o
        assert (grp.true_log_hazard_effect > 0).mean() > 0.01, o


def test_clv_truth_sane(sim):
    df = pd.read_parquet(Path(sim["paths"]["truth"]) / "clv_truth.parquet")
    assert len(df) == N_TEST
    assert (df.true_clv_margin_12m >= 0).all()
    assert (df.loc[~df.alive_at_end, "true_clv_margin_12m"] == 0).all()
    alive = df[df.alive_at_end]
    assert alive.true_clv_margin_12m.median() > 0


def test_ground_truth_firewall():
    """Only nodi.simulate (writer) and nodi.validate (validator) may reference ground truth."""
    offenders = []
    for py in (ROOT / "src" / "nodi").rglob("*.py"):
        rel = py.relative_to(ROOT / "src" / "nodi").parts
        if rel[0] in ("simulate", "validate") or py.name == "config.py":
            continue
        text = py.read_text(encoding="utf-8")
        if "ground_truth" in text or '["truth"]' in text or "'truth'" in text or "_truth.parquet" in text:
            offenders.append(str(py))
    for py in (ROOT / "app").rglob("*.py") if (ROOT / "app").exists() else []:
        if "ground_truth" in py.read_text(encoding="utf-8"):
            offenders.append(str(py))
    assert not offenders, offenders


def test_raw_data_contains_no_hidden_traits(sim):
    hidden = {"engagement", "price_sensitivity", "competitor_pull", "contact_fatigue",
              "network_quality", "has_other_sim", "log_base_hazard"}
    for f in Path(sim["paths"]["raw"]).rglob("*.parquet"):
        cols = set(pd.read_parquet(f).columns) if f.stat().st_size < 5e7 else set()
        assert not cols & hidden, f
