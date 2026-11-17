"""Export the small, precomputed files the Streamlit app reads (app_data/).

The app never touches the warehouse or ground truth. Everything it shows comes from here:
governed metrics (metrics.yml), model and plan outputs, and the validation summaries already
written to reports/ by nodi.validate. Counts and taka are stored at SAMPLE level plus the
operator scale factor; the app multiplies.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from nodi.config import ROOT
from nodi.metrics import Metrics
from nodi.models.run import SCORE_DATE
from nodi.offers import optimise as O
from nodi.offers.engine import eligible
from nodi.warehouse.build import connect

APP_DATA = ROOT / "app_data"


def _read_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def export_app_data(cfg: dict, out: Path | None = None) -> dict:
    out = out or APP_DATA
    out.mkdir(parents=True, exist_ok=True)
    rep = Path(cfg["paths"]["reports"])
    bc = cfg["budget"]
    con = connect(cfg)
    m = Metrics(con)

    # ---------------- base health (governed metrics)
    kpis = m.many(["active_base", "paying_subscribers", "net_revenue", "arpu", "arpu_active_base",
                   "churn_rate", "dormancy_rate", "recharge_frequency", "churners"])
    kpis.to_parquet(out / "kpis.parquet", index=False)
    val = {n: float(m.get(n, by=[]).iloc[0, 0]) for n in
           ["scored_subscribers", "expected_churners", "revenue_at_risk", "net_revenue_at_risk",
            "value_if_retained", "clv_12m"]}

    # ---------------- segments + plan coverage
    from nodi.segments.build import segment_profile
    seg = segment_profile(cfg)
    cover = con.execute("""
        SELECT segment_id, COUNT(*) FILTER (WHERE NOT holdout) AS plan_targeted,
               COUNT(*) FILTER (WHERE holdout) AS plan_holdout,
               SUM(cost) FILTER (WHERE NOT holdout) AS plan_spend, SUM(net) FILTER (WHERE NOT holdout) AS plan_net
        FROM mart_plan GROUP BY 1""").df()
    seg = seg.merge(cover, on="segment_id", how="left").fillna({"plan_targeted": 0, "plan_holdout": 0,
                                                                 "plan_spend": 0.0, "plan_net": 0.0})
    seg.to_parquet(out / "segments.parquet", index=False)

    # ---------------- subscriber-level arrays for the live budget slider
    subs = con.execute("""
        SELECT s.sub_id, g.segment_id, g.stance, s.churn_prob_90d, s.value_if_retained_12m
        FROM ml_scores s JOIN ml_segments g USING (sub_id) ORDER BY s.sub_id""").df()
    scores = con.execute("SELECT sub_id, offer_id, value, cost, cost_face, net, net_face FROM ml_offer_scores").df()
    steps = con.execute("""SELECT sub_id, offer_id, d_cost, d_net, ratio, cum_cost, cum_net
                           FROM ml_plan_steps ORDER BY ratio DESC, sub_id""").df()
    s = con.execute("""SELECT stddev_samp(margin_90d), stddev_samp(1 - churned::INT)
                       FROM mart_pilot_outcome WHERE arm = 'control'""").fetchone()
    sigma = {"margin": float(s[0]), "retention": float(s[1])}  # for the app's live holdout power calc
    con.close()
    summary5 = _read_json(rep / "phase5" / "summary.json") or {}
    best = summary5.get("best_single_offer", "recharge_cashback")
    elig = eligible(subs, cfg).sort_values("sub_id").reset_index(drop=True)
    b = scores[scores.offer_id == best].set_index("sub_id")
    elig["best_cost"] = b.cost.reindex(elig.sub_id).to_numpy()
    elig["best_net"] = b.net.reindex(elig.sub_id).to_numpy()
    elig["risk_rank"] = elig.churn_prob_90d.rank(ascending=False, method="first").astype(int)
    rnd = elig.sample(frac=1, random_state=1).sub_id.to_numpy()        # same order as engine.baselines
    elig["random_rank"] = pd.Series(np.arange(1, len(rnd) + 1), index=rnd).reindex(elig.sub_id).to_numpy()
    elig[["sub_id", "segment_id", "churn_prob_90d", "best_cost", "best_net", "risk_rank", "random_rank"]] \
        .to_parquet(out / "baseline_subscribers.parquet", index=False)

    steps["offer_id"] = steps.offer_id.astype("category")
    steps.to_parquet(out / "plan_steps.parquet", index=False)
    sf = scores[scores.sub_id.isin(elig.sub_id)][["sub_id", "offer_id", "cost_face", "net_face"]] \
        .rename(columns={"cost_face": "cost", "net_face": "net"})
    steps_face = O.hull_steps(sf)
    steps_face["offer_id"] = steps_face.offer_id.astype("category")
    steps_face[["sub_id", "offer_id", "d_cost", "d_net", "ratio", "cum_cost", "cum_net"]] \
        .to_parquet(out / "plan_steps_face.parquet", index=False)
    subs[["sub_id", "segment_id"]].to_parquet(out / "subscriber_segment.parquet", index=False)

    # ---------------- pilot, power, validation
    for name in ("pilot_readout", "holdout_power", "uplift_chosen", "frontier_model"):
        p = rep / "phase5" / f"{name}.csv"
        if p.exists():
            pd.read_csv(p).to_parquet(out / f"{name}.parquet", index=False)
    from nodi.validate.app_summary import validation_summary  # truth-derived: assembled inside nodi.validate
    validation = validation_summary(cfg)

    headline = {
        "score_date": str(SCORE_DATE), "operator_scale": bc["operator_scale"],
        "budget_bdt": bc["quarterly_bdt"], "slider_max_bdt": bc["slider_max_bdt"],
        "holdout_share": bc["holdout_share"], "best_single_offer": best,
        "excluded_stances": cfg["offers"].get("excluded_stances", []),
        "base": {"active_base_end": float(kpis.active_base.iloc[-1]),
                 "arpu_last6": float(kpis.arpu.tail(6).mean()),
                 "arpu_active_last6": float(kpis.arpu_active_base.tail(6).mean()),
                 "churn_rate_avg": float(kpis.churn_rate.mean()),
                 "churn_rate_last6": float(kpis.churn_rate.tail(6).mean()),
                 **val},
        "plans": summary5.get("plans_operator"),
        "max_profitable_spend_bdt": summary5.get("max_profitable_spend_operator_bdt"),
        "max_net_bdt": summary5.get("max_net_operator_bdt"),
        "pilot_ipw": summary5.get("pilot_ipw_net_per_pilot_sub"),
        "sigma_margin_90d": sigma["margin"], "sigma_retention": sigma["retention"],
        "cmo_metric": "Net contribution margin per Tk of offer cost, measured against a randomised 5% holdout "
                      "(read at 90 days, projected to 12 months). Retention vs holdout is a guardrail.",
    }
    (out / "headline.json").write_text(json.dumps(headline, indent=1, default=float), encoding="utf-8")
    (out / "validation.json").write_text(json.dumps(validation, indent=1, default=float), encoding="utf-8")
    sizes = {p.name: p.stat().st_size for p in out.rglob("*") if p.is_file()}
    return {"files": len(sizes), "total_mb": round(sum(sizes.values()) / 1e6, 2)}
