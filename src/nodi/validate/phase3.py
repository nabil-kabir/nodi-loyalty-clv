"""Phase 3 validation: do the churn and CLV models recover the planted truth?

Compares production scores (2026-07-01) with the hidden 12-month future:
- churn: predicted 90-day churn probability vs the true probability of a churn decision
- drivers: does model risk line up with each planted hazard component?
- CLV: BG/NBD + Gamma-Gamma and the run-rate baseline vs true 12-month contribution margin
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from nodi.viz import ACCENT, ACCENT2, GRID, MUTED, footer, plt, style
from nodi.warehouse.build import connect

DRIVERS = {
    "drv_wallet_share": "Losing wallet share to a second SIM",
    "drv_engagement": "Low engagement (hidden trait)",
    "drv_network_quality": "Weak network in their area",
    "drv_tenure": "Short tenure",
    "drv_new_sub": "First 90 days after activation",
    "drv_kiosk": "Activation-kiosk acquisition (first 6 months)",
    "drv_base": "Idiosyncratic base hazard (pure noise to the model)",
}


def phase3_validation(cfg: dict) -> dict:
    out = Path(cfg["paths"]["reports"]) / "phase3"
    out.mkdir(parents=True, exist_ok=True)
    truth = Path(cfg["paths"]["truth"])
    con = connect(cfg)
    s = con.execute("SELECT * FROM ml_scores").df()
    div = con.execute("SELECT sub_id, division FROM dim_subscriber").df()
    con.close()
    clv = pd.read_parquet(truth / "clv_truth.parquet")
    sub = pd.read_parquet(truth / "subscriber_truth.parquet")
    d = s.merge(clv, on="sub_id").merge(sub, on="sub_id").merge(div, on="sub_id")
    res = {}

    # ---------------- churn vs truth
    d["true_p"] = d.true_p_churn_90d.fillna(1.0)  # not alive in truth = certain churner
    dec = d.groupby("churn_decile").agg(pred=("churn_prob_90d", "mean"), true=("true_p", "mean"),
                                        n=("sub_id", "size")).reset_index()
    top10 = d.churn_decile == 1
    res["churn"] = {
        "spearman_pred_vs_true_p": float(spearmanr(d.churn_prob_90d, d.true_p).statistic),
        "mean_pred": float(d.churn_prob_90d.mean()), "mean_true_p": float(d.true_p.mean()),
        "top_decile_share_of_expected_churners": float(d.loc[top10, "true_p"].sum() / d.true_p.sum()),
    }

    # ---------------- drivers: planted component vs model score
    rows = []
    for col, label in DRIVERS.items():
        rho = spearmanr(d[col], d.churn_prob_90d).statistic
        rows.append({"planted_driver": label, "component": col,
                     "spearman_with_model_risk": float(rho),
                     "recovered": "yes" if rho > 0.1 else ("weak" if rho > 0.03 else "no")})
    drv = pd.DataFrame(rows)
    nq = d.groupby("division").agg(nq=("network_quality", "mean"), risk=("churn_prob_90d", "mean"))
    res["drivers"] = {"table": rows,
                      "division_rank_corr_network_vs_risk": float(spearmanr(-nq.nq, nq.risk).statistic)}
    drv.to_csv(out / "truth_driver_recovery.csv", index=False)

    # ---------------- CLV vs truth
    tv = d.true_clv_margin_12m
    clv_res = {}
    for name, col in [("bgnbd_gg", "clv_12m_pred"), ("run_rate", "clv_12m_baseline")]:
        pv = d[col]
        top = pv.rank(ascending=False, method="first") <= 0.2 * len(pv)
        clv_res[name] = {
            "spearman": float(spearmanr(pv, tv).statistic),
            "mae": float((pv - tv).abs().mean()),
            "total_bias": float(pv.sum() / tv.sum() - 1),
            "top20_true_value_capture": float(tv[top].sum() / tv.sum()),
        }
    oracle_top = tv.rank(ascending=False, method="first") <= 0.2 * len(tv)
    clv_res["oracle_top20_capture"] = float(tv[oracle_top].sum() / tv.sum())
    res["clv"] = clv_res

    # ---------------- charts
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    ax = axes[0]
    xs = np.arange(1, 11)
    ax.bar(xs, dec.true * 100, color="#99d5cf", label="Planted truth (hidden)")
    ax.plot(xs, dec.pred * 100, color=ACCENT, marker="o", label="Model prediction")
    ax.set_xticks(xs)
    ax.set_xlabel("Model risk decile (1 = riskiest)", color=MUTED, fontsize=8)
    ax.set_ylabel("90-day churn probability (%)", color=MUTED, fontsize=8)
    ax.legend(fontsize=8, frameon=False)
    style(ax, "Churn risk vs planted truth", f"Spearman {res['churn']['spearman_pred_vs_true_p']:.2f}, scored 2026-07-01")
    ax = axes[1]
    d["clv_dec"] = pd.qcut(d.clv_12m_pred.rank(method="first"), 10, labels=False) + 1
    cd = d.groupby("clv_dec").agg(true=("true_clv_margin_12m", "mean"), bg=("clv_12m_pred", "mean")).reset_index()
    d["base_dec"] = pd.qcut(d.clv_12m_baseline.rank(method="first"), 10, labels=False) + 1
    bd = d.groupby("base_dec").agg(true=("true_clv_margin_12m", "mean"), base=("clv_12m_baseline", "mean")).reset_index()
    ax.bar(cd.clv_dec, cd.true, color="#99d5cf", label="Planted true CLV (hidden)")
    ax.plot(cd.clv_dec, cd.bg, color=ACCENT, marker="o", label="BG/NBD + Gamma-Gamma")
    ax.plot(bd.base_dec, bd.base, color=ACCENT2, marker="s", ls="--", lw=1.2, label="Run-rate baseline")
    ax.set_xticks(xs)
    ax.set_xlabel("Predicted CLV decile (10 = most valuable)", color=MUTED, fontsize=8)
    ax.set_ylabel("12-month contribution margin (৳)", color=MUTED, fontsize=8)
    ax.legend(fontsize=8, frameon=False)
    style(ax, "12-month CLV vs planted truth",
          f"Spearman: BG/NBD {clv_res['bgnbd_gg']['spearman']:.2f}, baseline {clv_res['run_rate']['spearman']:.2f}")
    footer(fig)
    fig.tight_layout()
    fig.savefig(out / "truth_validation.png", dpi=160)
    plt.close(fig)

    lines = ["# Phase 3: validation against planted truth (synthetic data)", "",
             "Production scores at 2026-07-01 compared with the hidden 12-month future that no model saw.", "",
             "## Churn", "",
             f"- Rank correlation between predicted and true 90-day churn probability: **{res['churn']['spearman_pred_vs_true_p']:.2f}**.",
             f"- Mean predicted {res['churn']['mean_pred']:.1%} vs mean true {res['churn']['mean_true_p']:.1%}. "
             "The definitions differ slightly: the model predicts *going silent*, the truth is the *decision* to leave.",
             f"- The model's riskiest 10% hold **{res['churn']['top_decile_share_of_expected_churners']:.0%}** of expected churners.",
             "", "## Were the planted churn drivers recovered?", "",
             "| Planted driver | Rank corr. with model risk | Recovered? |", "|---|---:|---|",
             *[f"| {r['planted_driver']} | {r['spearman_with_model_risk']:+.2f} | {r['recovered']} |" for r in rows],
             "", f"- Division ranking: weak-network divisions carry higher model risk "
                 f"(rank corr. {res['drivers']['division_rank_corr_network_vs_risk']:+.2f} across the 8 divisions).",
             "", "## CLV", "",
             "| Model | Spearman vs truth | MAE ৳ | Total bias | True value in predicted top 20% |", "|---|---:|---:|---:|---:|",
             *[f"| {n} | {m['spearman']:.3f} | {m['mae']:.0f} | {m['total_bias']:+.1%} | {m['top20_true_value_capture']:.0%} |"
               for n, m in [("BG/NBD + Gamma-Gamma", clv_res["bgnbd_gg"]), ("Run-rate baseline", clv_res["run_rate"])]],
             f"| Perfect foresight (ceiling) | 1.000 | 0 | 0% | {clv_res['oracle_top20_capture']:.0%} |"]
    (out / "truth_validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "truth_validation.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    return res
