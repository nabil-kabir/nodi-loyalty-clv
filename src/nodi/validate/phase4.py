"""Phase 4 validation: are the segments real differences in the planted truth?

For each segment, compare predicted with true churn probability, CLV and margin at risk, and show
the planted response mix and true incremental margin per offer. This is VALIDATION ONLY:
Phase 5 must choose offers from the uplift models, never from this table.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from nodi.viz import ACCENT, GRID, MUTED, footer, plt, style
from nodi.warehouse.build import connect


def phase4_validation(cfg: dict) -> pd.DataFrame:
    out = Path(cfg["paths"]["reports"]) / "phase4"
    out.mkdir(parents=True, exist_ok=True)
    truth = Path(cfg["paths"]["truth"])
    con = connect(cfg)
    seg = con.execute("""SELECT g.sub_id, g.segment_id, g.segment, g.margin_at_risk_bdt,
                                s.churn_prob_90d, s.clv_12m_pred
                         FROM ml_segments g JOIN ml_scores s USING (sub_id)""").df()
    con.close()
    clv = pd.read_parquet(truth / "clv_truth.parquet")
    tt = pd.read_parquet(truth / "treatment_truth.parquet")
    d = seg.merge(clv, on="sub_id")
    d["true_p"] = d.true_p_churn_90d.fillna(1.0)
    d["true_mar"] = d.true_p * d.true_margin_if_retained_12m   # same construction as the model's

    s = d.groupby(["segment_id", "segment"]).agg(
        subs=("sub_id", "size"),
        pred_churn=("churn_prob_90d", "mean"), true_churn=("true_p", "mean"),
        pred_clv=("clv_12m_pred", "mean"), true_clv=("true_clv_margin_12m", "mean"),
        pred_mar=("margin_at_risk_bdt", "sum"), true_mar=("true_mar", "sum"),
    ).reset_index()
    s["pred_mar_share"] = s.pred_mar / s.pred_mar.sum()
    s["true_mar_share"] = s.true_mar / s.true_mar.sum()

    r = tt.merge(seg[["sub_id", "segment_id"]], on="sub_id")
    mix = (r.assign(persuadable=r.response_group == "persuadable", sleeping_dog=r.response_group == "sleeping_dog",
                    sure_thing=r.response_group == "sure_thing")
           .groupby(["segment_id", "offer_id"])
           .agg(persuadable=("persuadable", "mean"), sleeping_dog=("sleeping_dog", "mean"),
                sure_thing=("sure_thing", "mean"),
                true_inc_margin_per_sub=("true_incremental_margin_12m_before_cost", "mean"))
           .reset_index())
    mix.round(4).to_csv(out / "truth_segment_offer.csv", index=False)
    s.round(4).to_csv(out / "truth_segment_check.csv", index=False)

    # chart: predicted vs true share of margin at risk + true incremental margin heat map
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), gridspec_kw={"width_ratios": [1, 1.2]})
    ax = axes[0]
    ys = np.arange(len(s))[::-1]
    ax.barh(ys + 0.2, s.true_mar_share * 100, 0.4, color="#99d5cf", label="Planted truth (hidden)")
    ax.barh(ys - 0.2, s.pred_mar_share * 100, 0.4, color=ACCENT, label="Model")
    ax.set_yticks(ys, [f"{i}. {n}" for i, n in zip(s.segment_id, s.segment)])
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.grid(axis="y", visible=False)
    style(ax, "Share of margin at risk: model vs truth")
    ax = axes[1]
    piv = mix.pivot(index="segment_id", columns="offer_id", values="true_inc_margin_per_sub").sort_index()
    lim = np.nanmax(np.abs(piv.to_numpy()))
    im = ax.imshow(piv.to_numpy(), cmap="BrBG", vmin=-lim, vmax=lim, aspect="auto")
    ax.set_xticks(range(piv.shape[1]), [c.replace("_", "\n") for c in piv.columns], fontsize=8)
    ax.set_yticks(range(piv.shape[0]), [f"{i}" for i in piv.index])
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = piv.iloc[i, j]
            ax.text(j, i, f"{v:+.0f}", ha="center", va="center", fontsize=8,
                    color="white" if abs(v) > 0.55 * lim else "#111827")
    ax.set_ylabel("Segment", color=MUTED, fontsize=8)
    style(ax, "PLANTED TRUTH: incremental 12m margin per sub, ৳",
          "Before offer cost. Validation only; Phase 5 must learn this from the pilot")
    ax.grid(False)
    footer(fig)
    fig.tight_layout()
    fig.savefig(out / "truth_segments.png", dpi=160)
    plt.close(fig)

    lines = ["# Phase 4: segments vs planted truth (synthetic data)", "",
             "| # | Segment | Pred churn | True churn | Pred CLV ৳ | True CLV ৳ | Pred % at risk | True % at risk |",
             "|---:|---|---:|---:|---:|---:|---:|---:|"]
    lines += [f"| {x.segment_id} | {x.segment} | {x.pred_churn:.0%} | {x.true_churn:.0%} | {x.pred_clv:,.0f} | "
              f"{x.true_clv:,.0f} | {x.pred_mar_share:.0%} | {x.true_mar_share:.0%} |" for x in s.itertuples()]
    lines += ["", "## Planted response mix by segment (validation only)", "",
              mix.pivot(index="segment_id", columns="offer_id", values="persuadable").round(3).to_string(),
              "", "Sleeping-dog share:", "",
              mix.pivot(index="segment_id", columns="offer_id", values="sleeping_dog").round(3).to_string()]
    (out / "truth_validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return s
