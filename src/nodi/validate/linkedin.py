"""Four LinkedIn-ready charts (1200x1200 PNG, large type for phone screens).

Lives in nodi.validate because two charts show results validated against the planted truth.
Inputs: app_data/ (governed outputs) and reports/ (validation summaries).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from nodi.config import ROOT
from nodi.viz import ACCENT, ACCENT2, INK, MUTED, plt

LIGHT, RED, GRID = "#99d5cf", "#b91c1c", "#e5e7eb"
FOOT = "Synthetic data · fictional operator 'Nodi Telecom' · github.com/nabil-kabir/nodi-loyalty-clv"


def _frame(title: str, subtitle: str):
    fig = plt.figure(figsize=(6, 6), dpi=200)
    fig.text(0.06, 0.95, title, fontsize=15, fontweight="bold", color=INK, va="top", wrap=True)
    fig.text(0.06, 0.835, subtitle, fontsize=9.5, color=MUTED, va="top", wrap=True)
    fig.text(0.06, 0.025, FOOT, fontsize=7, color=MUTED)
    return fig


def _clean(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)


def make_linkedin_charts(cfg: dict) -> list[Path]:
    out = Path(cfg["paths"]["reports"]) / "linkedin"
    out.mkdir(parents=True, exist_ok=True)
    app = ROOT / "app_data"
    v = json.loads((app / "validation.json").read_text(encoding="utf-8"))
    h = json.loads((app / "headline.json").read_text(encoding="utf-8"))
    paths = []

    # 1. lead insight -------------------------------------------------------
    t = v["plans_vs_truth"]
    rows = [("Cashback to the\nhighest churn risk", t["highest_churn_risk"]["truth"], ACCENT2),
            ("Blanket cashback", t["blanket"]["truth"], MUTED),
            ("Bonus data to those\nthe uplift model picks", t["optimised"]["truth"], ACCENT)]
    fig = _frame("The customers most likely to churn are the worst place to spend a retention budget",
                 "Same ৳1 crore quarterly budget, three ways to spend it. True 12-month incremental margin after "
                 "offer cost, measured against the hidden counterfactual of a simulated market.")
    ax = fig.add_axes([0.32, 0.12, 0.6, 0.6])
    ys = np.arange(len(rows))
    vals = [r[1] / 1e7 for r in rows]
    ax.barh(ys, vals, color=[r[2] for r in rows], height=0.55)
    ax.set_yticks(ys, [r[0] for r in rows], fontsize=10, color=INK)
    ax.axvline(0, color=MUTED, lw=0.8)
    for y, x in zip(ys, vals):  # labels always to the right of the bar end or the zero line
        ax.text(max(x, 0) + 0.12, y, f"{'−' if x < 0 else ''}৳{abs(x):.1f} cr",
                va="center", ha="left", fontsize=12, fontweight="bold", color=RED if x < 0 else INK)
    ax.set_xlim(min(vals) - 0.3, max(vals) + 1.6)
    ax.set_xticks([])
    _clean(ax)
    ax.spines["bottom"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    paths.append(out / "1_riskiest_not_best.png")
    fig.savefig(paths[-1])
    plt.close(fig)

    # 2. risk vs where the plan spends ---------------------------------------
    seg = pd.read_parquet(app / "segments.parquet").sort_values("segment_id")
    seg = seg[seg.stance != "no_spend"]
    seg["coverage"] = seg.plan_targeted / seg.scored_subscribers
    fig = _frame("The plan spends where offers change behaviour, not where churn is highest",
                 "Each bubble is a customer segment (size = subscribers). The most at-risk segment is mostly already "
                 "gone, so the optimiser gives offers to only 8% of it.")
    ax = fig.add_axes([0.13, 0.13, 0.8, 0.6])
    ax.scatter(seg.avg_churn_prob * 100, seg.coverage * 100, s=seg.scored_subscribers / 60,
               color=[ACCENT2 if i == 1 else ACCENT for i in seg.segment_id], alpha=0.75, edgecolor="white")
    for r in seg.itertuples():
        right_edge = r.avg_churn_prob > 0.5
        big = r.scored_subscribers > 50_000
        ax.annotate(r.segment, (r.avg_churn_prob * 100, r.coverage * 100), fontsize=8.5, color=INK,
                    xytext=(-4, 22) if right_edge else (22, -14) if big else (8, 6), textcoords="offset points",
                    ha="right" if right_edge else "left")
    ax.set_xlabel("Average 90-day churn probability (%)", fontsize=9, color=MUTED)
    ax.set_ylabel("Share of segment receiving an offer (%)", fontsize=9, color=MUTED)
    ax.set_xlim(0, 85)
    ax.set_ylim(0, max(45, seg.coverage.max() * 120))
    ax.grid(color=GRID, lw=0.6)
    _clean(ax)
    paths.append(out / "2_risk_vs_spend.png")
    fig.savefig(paths[-1])
    plt.close(fig)

    # 3. what the pilot proved ------------------------------------------------
    r = pd.read_parquet(app / "pilot_readout.parquet")
    fig = _frame("In a randomised pilot, offers bought extra top-ups, not loyalty",
                 "8,000 subscribers per offer vs a control group. Retention moved by under 1 point for every offer; "
                 "the measurable payoff was extra spend, and only two offers covered their cost.")
    ax1 = fig.add_axes([0.30, 0.45, 0.62, 0.24])
    ax2 = fig.add_axes([0.30, 0.11, 0.62, 0.24])
    ys = np.arange(len(r))
    ax1.barh(ys, r.retention_uplift_pp, xerr=1.96 * r.retention_uplift_se_pp, color=LIGHT, ecolor=MUTED, capsize=3,
             height=0.55)
    ax1.set_yticks(ys, r.offer, fontsize=9.5, color=INK)
    ax1.axvline(0, color=MUTED, lw=0.8)
    ax1.set_title("Retention uplift, percentage points (95% CI)", fontsize=9.5, color=INK, loc="left")
    ax2.barh(ys, r.net_per_targeted_economic, color=[ACCENT if x > 0 else RED for x in r.net_per_targeted_economic],
             height=0.55)
    for y, x in zip(ys, r.net_per_targeted_economic):
        ax2.text(x + (0.8 if x >= 0 else -0.8), y, f"{'+' if x >= 0 else '−'}৳{abs(x):.0f}", va="center",
                 ha="left" if x >= 0 else "right", fontsize=9.5, color=INK)
    ax2.set_yticks(ys, r.offer, fontsize=9.5, color=INK)
    ax2.axvline(0, color=MUTED, lw=0.8)
    ax2.set_xlim(r.net_per_targeted_economic.min() - 9, r.net_per_targeted_economic.max() + 9)
    ax2.set_title("Extra 90-day margin per targeted subscriber, after offer cost (৳)", fontsize=9.5, color=INK, loc="left")
    for a in (ax1, ax2):
        _clean(a)
    paths.append(out / "3_pilot_spend_not_loyalty.png")
    fig.savefig(paths[-1])
    plt.close(fig)

    # 4. validated, and why calibration matters ---------------------------------
    fr = pd.read_csv(Path(cfg["paths"]["reports"]) / "phase5" / "frontier_truth.csv")
    sc = h["operator_scale"] / 1e7
    fig = _frame("Uplift models only pay off once you stop trusting their raw scores",
                 "True 12-month margin by budget, validated against the planted truth. Raw uplift scores promised "
                 f"৳{t['naive_uplift']['model'] / 1e7:.0f} crore at ৳1 crore and delivered ৳{t['naive_uplift']['truth'] / 1e7:.1f} crore; "
                 "calibrated, shrunk effects under-promise and over-deliver.")
    ax = fig.add_axes([0.13, 0.13, 0.8, 0.6])
    x = fr.budget_operator / 1e7
    ax.plot(x, fr.optimised * sc, color=ACCENT, lw=2.8, label="Calibrated uplift plan (truth)")
    ax.plot(x, fr.optimised_model * sc, color=ACCENT, lw=1.2, ls="--", label="…its own estimate (conservative)")
    ax.plot(x, fr.naive_uplift * sc, color=RED, lw=1.6, ls=":", label="Raw uplift scores (truth)")
    ax.plot(x, fr.blanket * sc, color=MUTED, lw=1.6, label="Blanket cashback (truth)")
    ax.plot(x, fr.highest_churn_risk * sc, color=ACCENT2, lw=1.6, label="Cashback to highest risk (truth)")
    ax.axhline(0, color=GRID, lw=1)
    ax.set_xlabel("Quarterly budget (৳ crore)", fontsize=9, color=MUTED)
    ax.set_ylabel("12-month net margin (৳ crore)", fontsize=9, color=MUTED)
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    ax.grid(color=GRID, lw=0.6)
    _clean(ax)
    paths.append(out / "4_calibration_matters.png")
    fig.savefig(paths[-1])
    plt.close(fig)
    return paths
