"""Phase 5 validation: does the optimised plan really beat the baselines in the planted truth?

Truth value of a plan = sum over targeted subscribers of the TRUE incremental 12-month margin of
their offer (hidden counterfactual simulation) minus the plan's expected offer cost.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from nodi.offers import engine as E
from nodi.offers import optimise as O
from nodi.offers import uplift as U
from nodi.simulate.catalog import OFFER_IDS
from nodi.viz import ACCENT, ACCENT2, GRID, MUTED, footer, plt, style
from nodi.warehouse.build import connect


def phase5_validation(cfg: dict) -> dict:
    out = Path(cfg["paths"]["reports"]) / "phase5"
    out.mkdir(parents=True, exist_ok=True)
    bc = cfg["budget"]
    scale = bc["operator_scale"]
    B = bc["quarterly_bdt"] / scale
    con = connect(cfg)
    S = con.execute("SELECT * FROM ml_offer_scores").df()
    steps = con.execute("SELECT * FROM ml_plan_steps ORDER BY ratio DESC, sub_id").df()
    seg = con.execute("SELECT sub_id, segment_id, segment FROM ml_segments").df()
    df = U.pilot_frame(con)
    X = E.production_frame(con, df)
    con.close()
    tt = pd.read_parquet(Path(cfg["paths"]["truth"]) / "treatment_truth.parquet")
    truth = tt[["sub_id", "offer_id", "true_incremental_margin_12m_before_cost", "true_uplift_retention",
                "response_group"]]
    best_offer = json.loads((out / "summary.json").read_text(encoding="utf-8"))["best_single_offer"]

    def true_net(plan):
        p = plan[["sub_id", "offer_id"]].merge(S[["sub_id", "offer_id", "cost"]], on=["sub_id", "offer_id"])
        p = p.merge(truth, on=["sub_id", "offer_id"], how="left").fillna({"true_incremental_margin_12m_before_cost": 0})
        return float(p.true_incremental_margin_12m_before_cost.sum() - p.cost.sum())

    # naive plan: raw T-learner scores
    rm = U.fit_redemption(df)
    Sn = E.naive_offer_scores(X, df, rm, cfg)
    steps_n = O.hull_steps(Sn[["sub_id", "offer_id", "cost", "net"]])

    budgets = np.linspace(bc["slider_max_bdt"] / scale / 60, bc["slider_max_bdt"] / scale, 30)
    rows = []
    for b in budgets:
        bl = E.baselines(X, S, b, best_offer)
        a = O.allocate(steps, b)
        an = O.allocate(steps_n, b)
        rows.append({"budget_operator": b * scale, "optimised": true_net(a), "optimised_model": a.net.sum(),
                     "naive_uplift": true_net(an), "naive_uplift_model": an.net.sum(),
                     "blanket": true_net(bl["blanket"]), "highest_churn_risk": true_net(bl["highest_churn_risk"])})
    fr = pd.DataFrame(rows)
    fr.round(1).to_csv(out / "frontier_truth.csv", index=False)

    plan = O.allocate(steps, B)
    bl = E.baselines(X, S, B, best_offer)
    an = O.allocate(steps_n, B)
    at_budget = {
        "optimised": {"model": plan.net.sum() * scale, "truth": true_net(plan) * scale},
        "naive_uplift": {"model": an.net.sum() * scale, "truth": true_net(an) * scale},
        "blanket": {"truth": true_net(bl["blanket"]) * scale},
        "highest_churn_risk": {"truth": true_net(bl["highest_churn_risk"]) * scale},
    }

    # uplift calibration vs truth, per offer
    v = S.merge(truth, on=["sub_id", "offer_id"])
    cal = []
    for o in OFFER_IDS:
        g = v[v.offer_id == o]
        cal.append({"offer_id": o, "pred_value_mean": g.value.mean(),
                    "true_value_mean": g.true_incremental_margin_12m_before_cost.mean(),
                    "spearman": spearmanr(g.value, g.true_incremental_margin_12m_before_cost).statistic
                    if g.value.std() > 0 else np.nan,
                    "true_retention_uplift_pp": g.true_uplift_retention.mean() * 100,
                    "true_persuadable": (g.response_group == "persuadable").mean(),
                    "true_sleeping_dog": (g.response_group == "sleeping_dog").mean()})
    cal = pd.DataFrame(cal)
    cal.round(4).to_csv(out / "truth_uplift_calibration.csv", index=False)

    # who did the plan pick, in truth? (segment 1 hypothesis from Phase 4)
    ps = plan.merge(seg, on="sub_id").merge(truth, on=["sub_id", "offer_id"], how="left")
    by_seg = ps.groupby(["segment_id", "segment"]).agg(
        targeted=("sub_id", "size"), true_inc_per_sub=("true_incremental_margin_12m_before_cost", "mean"),
        sleeping_dog=("response_group", lambda s: (s == "sleeping_dog").mean())).reset_index()
    by_seg.round(3).to_csv(out / "truth_plan_by_segment.csv", index=False)

    # chart
    fig, ax = plt.subplots(figsize=(9.5, 5))
    x = fr.budget_operator / 1e7
    k = scale / 1e7
    ax.plot(x, fr.optimised * k, color=ACCENT, lw=2.6, label="Optimised plan (truth)")
    ax.plot(x, fr.optimised_model * k, color=ACCENT, lw=1, ls="--", label="Optimised plan (model's own estimate)")
    nice = best_offer.replace("_", " ")
    ax.plot(x, fr.blanket * k, color=MUTED, lw=1.5, label=f"Blanket {nice}, random order (truth)")
    ax.plot(x, fr.highest_churn_risk * k, color=ACCENT2, lw=1.5, label=f"{nice.capitalize()} to highest churn risk (truth)")
    ax.plot(x, fr.naive_uplift * k, color="#b91c1c", lw=1.5, ls=":", label="Raw uplift scores, no calibration (truth)")
    ax.axhline(0, color="#d1d5db", lw=0.8)
    ax.axvline(bc["quarterly_bdt"] / 1e7, color="#d1d5db", lw=1)
    ax.set_xlabel("Quarterly budget (৳ crore, operator scale)", color=MUTED, fontsize=8)
    ax.set_ylabel("TRUE 12-month incremental margin, net of cost (৳ crore)", color=MUTED, fontsize=8)
    ax.legend(fontsize=7.5, frameon=False, loc="upper left")
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    o_ = at_budget["optimised"]["truth"] / 1e7
    b_ = at_budget["blanket"]["truth"] / 1e7
    style(ax, f"At ৳1 crore the optimised plan earns ৳{o_:.1f} crore vs ৳{b_:.1f} crore for a blanket offer",
          "Validated against the planted truth: the hidden counterfactual no model saw")
    footer(fig)
    fig.tight_layout()
    fig.savefig(out / "truth_frontier.png", dpi=160)
    plt.close(fig)

    lines = ["# Phase 5: plans vs planted truth (synthetic data)", "",
             "## At the ৳1 crore budget (operator scale)", "",
             "| Plan | Model estimate | TRUE net 12m margin |", "|---|---:|---:|",
             *[f"| {k_} | {('৳%.2f cr' % (v_['model'] / 1e7)) if 'model' in v_ else '-'} | ৳{v_['truth'] / 1e7:.2f} cr |"
               for k_, v_ in at_budget.items()], "",
             "## Uplift: predicted vs true incremental 12m margin per subscriber (before cost)", "",
             cal.round(3).to_string(index=False), "",
             "## Who the plan targets, in truth", "", by_seg.round(3).to_string(index=False)]
    (out / "truth_validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    res = {"at_budget": at_budget, "calibration": cal.to_dict("records")}
    (out / "truth_validation.json").write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")
    return res
