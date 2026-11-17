"""Offer engine: score every active subscriber x offer, build optimiser steps, baselines.

Everything here uses observable data only (pilot + production features + Phase 3/4 scores).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from nodi.models.features import CATEGORICAL, snapshot
from nodi.models.run import SCORE_DATE
from nodi.simulate.catalog import OFFER_IDS

from . import optimise as O
from . import uplift as U


def production_frame(con, pilot: pd.DataFrame) -> pd.DataFrame:
    X = snapshot(con, SCORE_DATE, with_label=False)
    for c in CATEGORICAL:
        X[c] = pd.Categorical(X[c].astype(str), categories=pilot[c].cat.categories)
    sc = con.execute("""SELECT s.sub_id, s.value_if_retained_12m, s.churn_prob_90d, s.churn_decile,
                               g.segment_id, g.segment, g.margin_at_risk_bdt
                        FROM ml_scores s JOIN ml_segments g USING (sub_id)""").df()
    return X.merge(sc, on="sub_id").sort_values("sub_id").reset_index(drop=True)


def offer_scores(X: pd.DataFrame, um: U.UpliftModel, rm: U.RedemptionModel, cfg: dict) -> pd.DataFrame:
    oc = cfg["offers"]
    rows = []
    for o in OFFER_IDS:
        p_red = rm.predict(o, X)
        # the redemption-based uplift candidate uses the same predicted redemption probability
        tau_m = um.effect(o, "margin", X)
        tau_r = um.effect(o, "retention", X)
        value = tau_m + tau_r * X.value_if_retained_12m.to_numpy() * U.CARRY_FORWARD
        c_econ = oc["contact_cost_bdt"] + p_red * oc["cost_per_redeemer"][o]["economic"]
        c_face = oc["contact_cost_bdt"] + p_red * oc["cost_per_redeemer"][o]["face"]
        rows.append(pd.DataFrame({
            "sub_id": X.sub_id.astype("int32"), "offer_id": o, "p_redeem": p_red,
            "tau_margin_90d": tau_m, "tau_retention": tau_r, "value": value,
            "cost": c_econ, "cost_face": c_face, "net": value - c_econ, "net_face": value - c_face,
        }))
    return pd.concat(rows, ignore_index=True)


def naive_offer_scores(X: pd.DataFrame, pilot: pd.DataFrame, rm: U.RedemptionModel, cfg: dict) -> pd.DataFrame:
    """What happens if you trust raw T-learner uplift scores (no calibration, no shrinkage).
    Used only to show the failure mode in the report, never for the plan."""
    oc = cfg["offers"]
    rows = []
    for o in OFFER_IDS:
        d, T = U._arm(pilot, o)
        tm = U.TLearnerScore().fit(d, T, d.margin_90d.to_numpy(float)).predict(X)
        tr = U.TLearnerScore().fit(d, T, d.retained.to_numpy(float)).predict(X)
        value = tm + tr * X.value_if_retained_12m.to_numpy() * U.CARRY_FORWARD
        cost = oc["contact_cost_bdt"] + rm.predict(o, X) * oc["cost_per_redeemer"][o]["economic"]
        rows.append(pd.DataFrame({"sub_id": X.sub_id.astype("int32"), "offer_id": o, "value": value,
                                  "cost": cost, "net": value - cost}))
    return pd.concat(rows, ignore_index=True)


def baselines(X: pd.DataFrame, scores: pd.DataFrame, budget: float, best_offer: str, seed: int = 1) -> dict:
    """Two plans a manager could run with the pilot's headline in hand: send the pilot's winning
    offer (best average net) to (a) the highest churn-risk subscribers, (b) everyone at random."""
    cost = scores[scores.offer_id == best_offer].set_index("sub_id").cost
    risk = X.sort_values("churn_prob_90d", ascending=False).sub_id.to_numpy()
    rnd = X.sample(frac=1, random_state=seed).sub_id.to_numpy()
    return {"highest_churn_risk": O.rank_and_fill(risk, best_offer, cost, budget),
            "blanket": O.rank_and_fill(rnd, best_offer, cost, budget)}


def plan_value(plan: pd.DataFrame, scores: pd.DataFrame) -> dict:
    """Model-estimated value of any plan (sub_id, offer_id)."""
    p = plan[["sub_id", "offer_id"]].merge(scores, on=["sub_id", "offer_id"], how="left")
    return {"targeted": len(p), "spend": float(p.cost.sum()), "spend_face": float(p.cost_face.sum()),
            "value": float(p.value.sum()), "net": float(p.net.sum())}
