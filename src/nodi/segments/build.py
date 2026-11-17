"""Assign every scored subscriber to exactly one segment and profile the segments.

Writes ml_segments to the warehouse and widens the scores_subscriber view so every metrics.yml
value metric can be sliced by segment.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from nodi.config import ROOT
from nodi.metrics import Metrics
from nodi.models.features import snapshot
from nodi.models.run import SCORE_DATE
from nodi.viz import ACCENT, ACCENT2, GRID, MUTED, footer, plt, style
from nodi.warehouse.build import connect

STAGES = ["gone_quiet", "new", "slipping", "steady"]
STANCE_COLOR = {"invest": ACCENT, "test": "#5eaaa0", "low_cost": "#99d5cf", "no_spend": "#d1d5db", "protect": "#9ca3af"}


def load_spec(path: Path | None = None) -> dict:
    with open(path or ROOT / "segments.yml", encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    cells = [tuple(c) for s in spec["segments"] for c in s["cells"]]
    expected = {(b, st) for b in ("High", "Medium", "Low") for st in STAGES}
    if sorted(cells) != sorted(expected):
        raise ValueError("segments.yml must map every (band, stage) cell exactly once")
    return spec


def assign(d: pd.DataFrame, spec: dict) -> pd.DataFrame:
    """d needs: clv_12m_pred, churn_prob_90d and the snapshot features. Returns d with segment columns."""
    th = spec["thresholds"]
    d = d.copy()
    d["margin_at_risk"] = d.value_if_retained_12m * d.churn_prob_90d
    rk = d.margin_at_risk.rank(ascending=False, method="first", pct=True)
    d["var_band"] = np.select([rk <= th["var_band_high"], rk <= th["var_band_medium"]], ["High", "Medium"], "Low")
    quiet = d.days_since_last_event >= th["quiet_days"]
    new = d.tenure_months < th["new_months"]
    slipping = ((d.active_days_30 < th["slipping_activity_ratio"] * d.active_days_prev30)
                | ((d.rech_prev30 >= 2) & (d.rech_30 < th["slipping_recharge_ratio"] * d.rech_prev30)))
    d["stage"] = np.select([quiet, new, slipping], STAGES[:3], STAGES[3])
    lookup = {tuple(c): s for s in spec["segments"] for c in s["cells"]}
    seg = [lookup[(b, st)] for b, st in zip(d.var_band, d.stage)]
    d["segment_id"] = [s["id"] for s in seg]
    d["segment"] = [s["name"] for s in seg]
    d["stance"] = [s["stance"] for s in seg]
    return d


def build_segments(cfg: dict) -> pd.DataFrame:
    spec = load_spec()
    con = connect(cfg, read_only=False)
    feats = snapshot(con, SCORE_DATE, with_label=False)
    scores = con.execute("SELECT * FROM ml_scores").df()
    d = assign(feats.merge(scores, on="sub_id"), spec)
    cm = cfg["economics"]["contribution_margin_on_net"]
    out = pd.DataFrame({
        "sub_id": d.sub_id.astype("int32"), "segment_id": d.segment_id.astype("int8"), "segment": d.segment,
        "var_band": d.var_band, "stage": d.stage, "stance": d.stance,
        "margin_at_risk_bdt": d.margin_at_risk,
        # net revenue equivalent of the margin at risk (CLV is in contribution margin)
        "net_revenue_at_risk_bdt": d.margin_at_risk / cm,
    })
    con.register("seg_df", out)
    con.execute("CREATE OR REPLACE TABLE ml_segments AS SELECT * FROM seg_df")
    con.execute(f"""CREATE OR REPLACE VIEW scores_subscriber AS
        SELECT s.*, DATE '{SCORE_DATE}' AS month_start, d.division, d.area_type, d.handset_tier,
               d.is_smartphone, d.acquisition_channel,
               g.segment_id, g.segment, g.var_band, g.stage, g.stance,
               g.margin_at_risk_bdt, g.net_revenue_at_risk_bdt
        FROM ml_scores s JOIN dim_subscriber d USING (sub_id) LEFT JOIN ml_segments g USING (sub_id)""")
    con.close()
    print(f"[segments] {len(out):,} subscribers in {out.segment_id.nunique()} segments", flush=True)
    return out


def segment_profile(cfg: dict) -> pd.DataFrame:
    """Sizing from metrics.yml plus a descriptive profile per segment."""
    spec = load_spec()
    con = connect(cfg)
    m = Metrics(con)
    by = ["segment_id", "segment"]
    size = m.many(["scored_subscribers", "expected_churners", "clv_12m", "revenue_at_risk",
                   "net_revenue_at_risk"], by=by)
    prof = con.execute(f"""
        SELECT g.segment_id,
               AVG(s.churn_prob_90d) AS avg_churn_prob,
               AVG(d.is_smartphone::INT) AS smartphone_share,
               median(datediff('month', d.activation_date, DATE '{SCORE_DATE}')) AS median_tenure_months,
               AVG((d.acquisition_channel = 'activation_kiosk')::INT) AS kiosk_share
        FROM ml_segments g JOIN ml_scores s USING (sub_id) JOIN dim_subscriber d USING (sub_id)
        GROUP BY 1""").df()
    div = con.execute("""
        WITH c AS (SELECT g.segment_id, d.division, COUNT(*) n
                   FROM ml_segments g JOIN dim_subscriber d USING (sub_id) GROUP BY 1, 2),
        s AS (SELECT segment_id, division, n / SUM(n) OVER (PARTITION BY segment_id) AS seg_share,
                     SUM(n) OVER (PARTITION BY division) / SUM(n) OVER () AS base_share FROM c)
        SELECT segment_id, arg_max(division, seg_share / base_share) AS over_indexed_division,
               MAX(seg_share / base_share) AS division_index
        FROM s GROUP BY 1""").df()
    con.close()
    prof = prof.merge(div, on="segment_id")
    p = size.merge(prof, on="segment_id").sort_values("segment_id").reset_index(drop=True)
    p["share_of_base"] = p.scored_subscribers / p.scored_subscribers.sum()
    p["share_of_margin_at_risk"] = p.revenue_at_risk / p.revenue_at_risk.sum()
    p["margin_at_risk_per_sub"] = p.revenue_at_risk / p.scored_subscribers
    meta = {s["id"]: s for s in spec["segments"]}
    p["stance"] = p.segment_id.map(lambda i: meta[i]["stance"])
    p["action"] = p.segment_id.map(lambda i: " ".join(meta[i]["action"].split()))
    return p


def phase4_report(cfg: dict) -> pd.DataFrame:
    out = Path(cfg["paths"]["reports"]) / "phase4"
    out.mkdir(parents=True, exist_ok=True)
    p = segment_profile(cfg)
    p.round(4).to_csv(out / "segment_profile.csv", index=False)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), gridspec_kw={"width_ratios": [1.5, 1]})
    ax = axes[0]
    ys = np.arange(len(p))[::-1]
    ax.barh(ys + 0.2, p.share_of_base * 100, 0.4, color="#d1d5db", label="% of active base")
    ax.barh(ys - 0.2, p.share_of_margin_at_risk * 100, 0.4, color=[STANCE_COLOR[s] for s in p.stance],
            label="% of margin at risk")
    ax.set_yticks(ys, [f"{i}. {n}" for i, n in zip(p.segment_id, p.segment)])
    for y, v in zip(ys, p.share_of_margin_at_risk):
        ax.text(v * 100 + 0.6, y - 0.2, f"{v:.0%}", va="center", fontsize=8, color="#374151")
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.grid(axis="y", visible=False)
    style(ax, "Where the ৳ at risk sits", "Grey: share of subscribers. Colour: share of 12-month margin at risk")
    ax = axes[1]
    ax.barh(ys, p.margin_at_risk_per_sub, color=[STANCE_COLOR[s] for s in p.stance])
    ax.set_yticks(ys, [""] * len(p))
    for y, v in zip(ys, p.margin_at_risk_per_sub):
        ax.text(v + 5, y, f"৳{v:,.0f}", va="center", fontsize=8, color="#374151")
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.grid(axis="y", visible=False)
    style(ax, "Margin at risk per subscriber", "Colour = stance: invest / test / low-cost / no-spend / protect")
    footer(fig)
    fig.tight_layout()
    fig.savefig(out / "segment_map.png", dpi=160)
    plt.close(fig)

    tot = p.revenue_at_risk.sum()
    lines = ["# Phase 4: value x risk segmentation (synthetic data)", "",
             f"Scored {int(p.scored_subscribers.sum()):,} active subscribers on {SCORE_DATE}. "
             f"Total 12-month margin at risk: ৳{tot / 1e5:,.1f} lakh "
             f"(net revenue equivalent ৳{p.net_revenue_at_risk.sum() / 1e5:,.1f} lakh). All sizes come from metrics.yml.", "",
             "| # | Segment | Subscribers | % base | Exp. churners (90d) | Avg CLV ৳ | Margin at risk ৳ lakh | % at risk | Stance | What we do |",
             "|---:|---|---:|---:|---:|---:|---:|---:|---|---|"]
    for r in p.itertuples():
        lines.append(f"| {r.segment_id} | **{r.segment}** | {r.scored_subscribers:,.0f} | {r.share_of_base:.0%} | "
                     f"{r.expected_churners:,.0f} | {r.clv_12m:,.0f} | {r.revenue_at_risk / 1e5:,.1f} | "
                     f"{r.share_of_margin_at_risk:.0%} | {r.stance.replace('_', ' ')} | {r.action} |")
    lines += ["", "## Profiles", "",
              p[["segment", "avg_churn_prob", "smartphone_share", "median_tenure_months", "kiosk_share",
                 "over_indexed_division", "division_index", "margin_at_risk_per_sub"]].round(3).to_string(index=False)]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p
