"""Phase 3 tests: CLV maths recovers known parameters, features are point-in-time, pipeline runs."""
import datetime as dt
import shutil
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

from nodi.metrics import Metrics
from nodi.models import clv as V
from nodi.models.churn import decile_table
from nodi.models.features import NUMERIC, snapshot
from nodi.warehouse.build import connect, db_path


# ---------------------------------------------------------------- CLV maths
def test_bgnbd_recovers_known_parameters():
    true = V.BGNBD(r=0.8, alpha=4.0, a=0.6, b=2.5)
    sim = true.simulate(5000, T=40, rng=np.random.default_rng(0))
    est = V.BGNBD.fit(sim.x, sim.t_x, sim["T"])
    assert est.r == pytest.approx(true.r, rel=0.15)
    assert est.alpha == pytest.approx(true.alpha, rel=0.2)
    # mean dropout probability a/(a+b)
    assert est.a / (est.a + est.b) == pytest.approx(true.a / (true.a + true.b), rel=0.3)


def test_bgnbd_predictions_behave():
    m = V.BGNBD(r=2.0, alpha=3.0, a=1.5, b=20.0)
    x = np.array([0, 5, 20, 20])
    t_x = np.array([0, 39, 39, 10])
    T = np.array([40, 40, 40, 40])
    e = m.expected_purchases(10, x, t_x, T)
    assert e[2] > e[1] > 0                      # recent + more frequent -> more future purchases
    assert e[3] < e[2]                          # same frequency but long silence -> fewer
    pa = m.p_alive(x, t_x, T)
    assert pa[0] == 1.0 and pa[3] < pa[2]       # x = 0 is "alive" by construction in BG/NBD


def test_gamma_gamma_recovers_population_mean():
    rng = np.random.default_rng(1)
    p, q, g = 4.0, 6.0, 40.0
    n = rng.integers(2, 60, 4000)
    nu = rng.gamma(q, 1 / g, 4000)
    m = np.array([rng.gamma(p, 1 / v, k).mean() for v, k in zip(nu, n)])
    est = V.GammaGamma.fit(n, m)
    assert est.population_mean == pytest.approx(p * g / (q - 1), rel=0.1)
    assert np.corrcoef(est.expected_value(n, m), p / nu)[0, 1] > 0.9


def test_decile_table_is_consistent():
    rng = np.random.default_rng(2)
    s = rng.random(10_000)
    y = (rng.random(10_000) < s).astype(int)
    t = decile_table(y, s)
    assert t.cum_capture.iloc[-1] == pytest.approx(1.0)
    assert t.churn_rate.is_monotonic_decreasing
    assert (t.subscribers.sum()) == 10_000


# ---------------------------------------------------------------- point-in-time features
def test_features_do_not_see_the_future(wh, tmp_path):
    T = dt.date(2025, 10, 1)
    con = connect(wh)
    before = snapshot(con, T, with_label=False).set_index("sub_id")
    con.close()
    cp = tmp_path / "wh.duckdb"
    shutil.copyfile(db_path(wh), cp)
    con = duckdb.connect(str(cp))
    for t in ("fct_recharge", "fct_daily_usage", "fct_pack_purchase", "fct_offer_exposure"):
        con.execute(f"DELETE FROM {t} WHERE date >= DATE '{T}'")
    after = snapshot(con, T, with_label=False).set_index("sub_id")
    con.close()
    cols = [c for c in NUMERIC if c not in ("dormant_spells_365", "ever_reactivated")]
    pd.testing.assert_frame_equal(before[cols], after.loc[before.index, cols])


def test_snapshot_population_is_the_active_base(wh):
    con = connect(wh)
    n = len(snapshot(con, dt.date(2026, 2, 1), with_label=False))
    k = Metrics(con).get("active_base", where="month_start = DATE '2026-02-01'")["active_base"].iloc[0]
    con.close()
    assert n == k


# ---------------------------------------------------------------- pipeline
@pytest.fixture(scope="module")
def modelled(wh):
    from nodi.models.run import run_models
    summary = run_models(wh)
    return wh, summary


def test_pipeline_writes_scores_and_unlocks_metrics(modelled):
    cfg, summary = modelled
    con = connect(cfg)
    s = con.execute("SELECT * FROM ml_scores").df()
    m = Metrics(con)
    clv = m.get("clv_12m", by=[])["clv_12m"].iloc[0]
    risk = m.get("revenue_at_risk", by=["division"])
    con.close()
    assert s.churn_prob_90d.between(0, 1).all()
    assert s.churn_decile.between(1, 10).all()
    assert (s.clv_12m_pred >= 0).all() and s.clv_12m_pred.notna().all()
    assert clv > 0 and len(risk) == 8
    assert summary["churn_backtest"]["lightgbm"]["auc"] > 0.65


def test_truth_validation_runs(modelled):
    from nodi.validate.phase3 import phase3_validation
    cfg, _ = modelled
    res = phase3_validation(cfg)
    assert res["clv"]["bgnbd_gg"]["spearman"] > 0.5
    assert res["churn"]["spearman_pred_vs_true_p"] > 0.2
