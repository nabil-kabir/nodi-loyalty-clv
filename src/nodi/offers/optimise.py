"""Budget allocation: maximise expected incremental margin net of offer cost, not response rate.

Each subscriber gets at most one offer (or nothing). For subscriber i and offer k:
    cost_ik = contact cost + P(redeem)_ik x cost per redeemer
    net_ik  = incremental value_ik (before cost) - cost_ik
Subject to sum(cost) <= budget. This is a multiple-choice knapsack. We solve its LP relaxation
greedily: for each subscriber, build the upper concave hull of (cost, net) from (0, 0), split it
into incremental steps, and take steps across all subscribers in order of net-per-taka until the
budget runs out or no step adds value. Steps are precomputed once, so a new budget is a single
cumulative-sum lookup (that is what makes the app's slider live).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def hull_steps(options: pd.DataFrame) -> pd.DataFrame:
    """options: sub_id, offer_id, cost, net. Returns incremental steps on each subscriber's hull."""
    opt = options[(options.net > 0) & (options.cost > 0)].sort_values(["sub_id", "cost"])
    rows = []
    for sub, g in opt.groupby("sub_id", sort=False):
        pts = [(0.0, 0.0, None)]
        for c, v, o in zip(g.cost.to_numpy(), g.net.to_numpy(), g.offer_id.to_numpy()):
            if v <= pts[-1][1]:
                continue  # dominated: costs more, adds no value
            while len(pts) >= 2:
                (c1, v1, _), (c2, v2, _) = pts[-2], pts[-1]
                if (v2 - v1) * (c - c1) <= (v - v1) * (c2 - c1):  # pts[-1] lies below the chord
                    pts.pop()
                else:
                    break
            pts.append((c, v, o))
        for (c1, v1, _), (c2, v2, o) in zip(pts[:-1], pts[1:]):
            rows.append((sub, o, c2 - c1, v2 - v1, c2, v2))
    st = pd.DataFrame(rows, columns=["sub_id", "offer_id", "d_cost", "d_net", "cost", "net"])
    st = st.astype({"sub_id": "int64", "offer_id": "object", "d_cost": float, "d_net": float,
                    "cost": float, "net": float})
    st["ratio"] = st.d_net / st.d_cost
    st = st.sort_values(["ratio", "sub_id"], ascending=[False, True], kind="stable").reset_index(drop=True)
    st["cum_cost"] = st.d_cost.cumsum()
    st["cum_net"] = st.d_net.cumsum()
    return st


def allocate(steps: pd.DataFrame, budget: float) -> pd.DataFrame:
    """Final offer per subscriber for a budget: the last hull step taken for that subscriber."""
    taken = steps[steps.cum_cost <= budget]
    return taken.groupby("sub_id", sort=False).tail(1)[["sub_id", "offer_id", "cost", "net"]].reset_index(drop=True)


def frontier(steps: pd.DataFrame, budgets: np.ndarray) -> pd.DataFrame:
    if steps.empty:  # nothing is worth doing at any budget
        return pd.DataFrame({"budget": budgets, "spend": 0.0, "expected_net_margin": 0.0})
    i = np.searchsorted(steps.cum_cost.to_numpy(), budgets, side="right") - 1
    spend = np.where(i >= 0, steps.cum_cost.to_numpy()[np.maximum(i, 0)], 0.0)
    net = np.where(i >= 0, steps.cum_net.to_numpy()[np.maximum(i, 0)], 0.0)
    return pd.DataFrame({"budget": budgets, "spend": spend, "expected_net_margin": net})


def rank_and_fill(order: np.ndarray, offer: str, cost: pd.Series, budget: float) -> pd.DataFrame:
    """Baseline helper: give `offer` to subscribers in `order` until the budget is used."""
    c = cost.loc[order].to_numpy()
    keep = np.cumsum(c) <= budget
    return pd.DataFrame({"sub_id": order[keep], "offer_id": offer, "cost": c[keep]})
