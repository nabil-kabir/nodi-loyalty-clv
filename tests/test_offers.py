"""Phase 5 tests: optimiser correctness, uplift calibration logic, power maths, pipeline."""
import numpy as np
import pandas as pd
import pytest

from nodi.metrics import Metrics
from nodi.offers import experiment as X
from nodi.offers import optimise as O
from nodi.offers.uplift import blp
from nodi.warehouse.build import connect


# ---------------------------------------------------------------- optimiser
def toy_options():
    # sub 1: cheap A (cost 2, net 4) and pricier B (cost 10, net 6): both on the hull
    # sub 2: A dominated (costs more than B for less net), only B (cost 3, net 3) survives
    # sub 3: nothing profitable
    return pd.DataFrame({
        "sub_id":   [1, 1, 2, 2, 3],
        "offer_id": ["A", "B", "A", "B", "A"],
        "cost":     [2.0, 10.0, 5.0, 3.0, 1.0],
        "net":      [4.0, 6.0, 2.0, 3.0, -1.0],
    })


def test_hull_steps_and_allocation():
    st = O.hull_steps(toy_options())
    assert set(st.sub_id) == {1, 2}
    assert list(st.ratio) == sorted(st.ratio, reverse=True)
    # ratios: sub1 A 2.0, sub2 B 1.0, sub1 A->B 2/8 = 0.25
    assert st.ratio.tolist() == pytest.approx([2.0, 1.0, 0.25])
    a = O.allocate(st, budget=5.0)          # A for sub 1 (2) + B for sub 2 (3)
    assert dict(zip(a.sub_id, a.offer_id)) == {1: "A", 2: "B"}
    a = O.allocate(st, budget=1000)          # everything: sub 1 upgrades to B
    assert dict(zip(a.sub_id, a.offer_id)) == {1: "B", 2: "B"}
    assert a.cost.sum() == pytest.approx(13.0)


def test_frontier_is_monotone_and_respects_budget():
    rng = np.random.default_rng(0)
    n = 500
    opts = pd.DataFrame({"sub_id": np.repeat(np.arange(n), 3), "offer_id": np.tile(["a", "b", "c"], n),
                         "cost": rng.uniform(1, 20, 3 * n), "net": rng.normal(2, 5, 3 * n)})
    st = O.hull_steps(opts)
    budgets = np.linspace(0, st.cum_cost.iloc[-1] * 1.2, 40)
    fr = O.frontier(st, budgets)
    assert (np.diff(fr.expected_net_margin) >= -1e-9).all()
    assert (fr.spend <= fr.budget + 1e-9).all()
    for b in budgets[1:]:
        a = O.allocate(st, b)
        assert a.cost.sum() <= b + 1e-9 and a.sub_id.is_unique


# ---------------------------------------------------------------- uplift calibration
def test_blp_finds_real_heterogeneity_and_rejects_noise():
    rng = np.random.default_rng(1)
    n = 20_000
    x = rng.normal(size=n)
    T = (rng.random(n) < 0.5).astype(float)
    y = 5 + 2 * x + T * (3 + 4 * x) + rng.normal(0, 10, n)
    real = blp(y, T, 3 + 4 * x + rng.normal(0, 1, n))
    noise = blp(y, T, rng.normal(size=n))
    assert real["beta2"] == pytest.approx(1.0, abs=0.15) and real["beta2"] / real["beta2_se"] > 5
    assert abs(noise["beta2"] / noise["beta2_se"]) < 3
    assert real["ate"] == pytest.approx(3.0, abs=0.5)


# ---------------------------------------------------------------- experiment design
def test_mde_matches_textbook_formula():
    # z(0.975) + z(0.8) = 1.95996 + 0.84162 = 2.80158
    assert X.mde(10.0, 1000, 1000) == pytest.approx(2.80158 * 10 * np.sqrt(2 / 1000), rel=1e-4)
    t = X.holdout_table(100_000, 20, 15, 300, 0.35, 0.5, shares=(0.02, 0.1))
    assert t.mde_margin_bdt_per_sub.is_monotonic_decreasing
    assert (t.forgone_net_margin_bdt == [2_000 * 15, 10_000 * 15]).all()


# ---------------------------------------------------------------- pipeline
def test_pipeline_plan_respects_budget_and_metrics_live(offered):
    cfg, summary = offered
    con = connect(cfg)
    m = Metrics(con)
    spend = m.get("planned_spend", by=[])["planned_spend"].iloc[0]
    roi = m.get("plan_roi", by=["segment"])
    plan = con.execute("SELECT * FROM ml_plan").df()
    con.close()
    sample_budget = cfg["budget"]["quarterly_bdt"] / cfg["budget"]["operator_scale"]
    assert (spend if spend == spend else 0) <= sample_budget + 1e-6   # NaN when the plan is empty
    assert plan.sub_id.is_unique
    assert "optimised" in summary["plans_operator"]
    if len(plan):
        # The tiny test pilot (~120 per arm) usually finds no significant effect, so an empty plan
        # ("spend nothing") is the correct answer there. With a plan, check the holdout and slicing.
        assert len(roi) >= 1
        assert plan.holdout.mean() == pytest.approx(cfg["budget"]["holdout_share"], abs=0.05)
    else:
        assert summary["plans_operator"]["optimised"]["spend_bdt"] == 0


def test_phase5_truth_validation_runs(offered):
    from nodi.validate.phase5 import phase5_validation
    cfg, _ = offered
    res = phase5_validation(cfg)
    assert {"optimised", "blanket", "highest_churn_risk", "naive_uplift"} <= set(res["at_budget"])
