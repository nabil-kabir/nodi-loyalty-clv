"""Phase 5 orchestrator: pilot readout -> uplift + redemption models -> offer scores ->
optimised plan with randomised holdout -> baselines -> experiment design -> persist + report.

Sample-level numbers are multiplied by budget.operator_scale for operator-level reporting
(DECISIONS B5.1). Uses observable data only; truth comparisons live in nodi.validate.phase5.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from nodi.models.run import SCORE_DATE
from nodi.simulate.catalog import OFFER_IDS, OFFERS
from nodi.viz import ACCENT, ACCENT2, GRID, MUTED, footer, plt, style
from nodi.warehouse.build import connect

from . import engine as E
from . import experiment as X_
from . import optimise as O
from . import uplift as U

OFFER_COLOR = {"bonus_data": ACCENT, "recharge_cashback": ACCENT2, "tenure_reward": "#9ca3af",
               "bundle_discount": "#6366f1"}
LABEL = dict(zip(OFFERS.offer_id, OFFERS.name))


def _log(m):
    print(f"[offers {time.strftime('%H:%M:%S')}] {m}", flush=True)


def crore(x):
    return x / 1e7


def run_offers(cfg: dict) -> dict:
    con = connect(cfg, read_only=False)
    try:  # never leave a write connection open: it locks the warehouse file
        return _run_offers(cfg, con)
    finally:
        con.close()


def _run_offers(cfg: dict, con) -> dict:
    out = Path(cfg["paths"]["reports"]) / "phase5"
    out.mkdir(parents=True, exist_ok=True)
    bc, oc = cfg["budget"], cfg["offers"]
    scale = bc["operator_scale"]
    B = bc["quarterly_bdt"] / scale

    # ------------------------------------------------ pilot: readout + models
    df = U.pilot_frame(con)
    oof = U.cross_fit_scores(df)
    um = U.fit_uplift(df, oof)
    rm = U.fit_redemption(df)
    _log("uplift + redemption models fitted on the pilot")
    readout = []
    for o in OFFER_IDS:
        cm = um.chosen[(um.chosen.offer_id == o) & (um.chosen.outcome == "margin")].iloc[0]
        cr = um.chosen[(um.chosen.offer_id == o) & (um.chosen.outcome == "retention")].iloc[0]
        red = df.loc[df.arm == o, "redeemed"].mean()
        ce = oc["contact_cost_bdt"] + red * oc["cost_per_redeemer"][o]["economic"]
        cf = oc["contact_cost_bdt"] + red * oc["cost_per_redeemer"][o]["face"]
        readout.append({"offer_id": o, "offer": LABEL[o], "margin_uplift_90d": cm.ate, "margin_uplift_se": cm.ate_se,
                        "retention_uplift_pp": cr.ate * 100, "retention_uplift_se_pp": cr.ate_se * 100,
                        "redemption_rate": red, "cost_per_targeted_economic": ce, "cost_per_targeted_face": cf,
                        "net_per_targeted_economic": cm.ate - ce, "net_per_targeted_face": cm.ate - cf,
                        "personalised_by": cm.candidate, "redemption_model_auc": rm.oof_auc[o]})
    readout = pd.DataFrame(readout)
    best_offer = readout.sort_values("net_per_targeted_economic", ascending=False).offer_id.iloc[0]

    # ------------------------------------------------ production scoring + optimiser
    X = E.production_frame(con, df)
    S = E.offer_scores(X, um, rm, cfg)
    steps = O.hull_steps(S[["sub_id", "offer_id", "cost", "net"]])
    plan = O.allocate(steps, B)
    rng = np.random.default_rng([cfg["seed"], 55])
    plan["holdout"] = rng.random(len(plan)) < bc["holdout_share"]
    _log(f"plan: {len(plan):,} sample subscribers at sample budget Tk{B:,.0f}")

    bl = E.baselines(X, S, B, best_offer)
    plans = {"optimised": plan, **bl}
    values = {k: E.plan_value(v, S) for k, v in plans.items()}

    budgets = np.linspace(0, bc["slider_max_bdt"] / scale, 61)
    fr = O.frontier(steps, budgets).rename(columns={"expected_net_margin": "optimised"})
    for name in ("highest_churn_risk", "blanket"):
        fr[name] = [E.plan_value(E.baselines(X, S, b, best_offer)[name], S)["net"] if b > 0 else 0.0 for b in budgets]
    fr.insert(0, "budget_operator", fr.budget * scale)

    # ------------------------------------------------ observable check on the pilot (IPW)
    Xp = df.copy()
    Xp["value_if_retained_12m"] = 0.0  # retention effects are zero after the significance rule
    Sp = E.offer_scores(Xp, um, rm, cfg)
    st_p = O.hull_steps(Sp[["sub_id", "offer_id", "cost", "net"]])
    Bp = B * len(df) / len(X)
    alloc_p = O.allocate(st_p, Bp).set_index("sub_id").offer_id
    assign_opt = df.sub_id.map(alloc_p).fillna("control").to_numpy()
    cost_p = Sp[Sp.offer_id == best_offer].set_index("sub_id").cost
    rnd = df.sample(frac=1, random_state=1).sub_id.to_numpy()
    blanket_p = O.rank_and_fill(rnd, best_offer, cost_p, Bp).set_index("sub_id").offer_id
    assign_bl = df.sub_id.map(blanket_p).fillna("control").to_numpy()
    cpr = {o: oc["cost_per_redeemer"][o]["economic"] for o in OFFER_IDS}
    ipw = {"optimised": U.policy_value_ipw(df, assign_opt, cpr, oc["contact_cost_bdt"]),
           "blanket": U.policy_value_ipw(df, assign_bl, cpr, oc["contact_cost_bdt"])}

    # ------------------------------------------------ experiment design
    treated = plan[~plan.holdout].merge(S, on=["sub_id", "offer_id"], suffixes=("", "_s"))
    ctrl = df[df.arm == "control"]
    gross_per = treated.value.mean()
    net_per = treated.net_s.mean() if "net_s" in treated else treated.net.mean()
    ht = X_.holdout_table(n_targeted=len(plan) * scale, expected_gross_per_sub=gross_per,
                          expected_net_per_sub=net_per, sigma_margin=ctrl.margin_90d.std(),
                          sigma_retention=ctrl.retained.std(), expected_ret_pp=treated.tau_retention.mean() * 100)

    # ------------------------------------------------ persist
    con.register("s_df", S)
    con.execute("CREATE OR REPLACE TABLE ml_offer_scores AS SELECT * FROM s_df")
    con.register("st_df", steps)
    con.execute("CREATE OR REPLACE TABLE ml_plan_steps AS SELECT * FROM st_df")
    con.register("p_df", plan[["sub_id", "offer_id", "holdout"]])
    con.execute("CREATE OR REPLACE TABLE ml_plan AS SELECT * FROM p_df")
    con.execute(f"""CREATE OR REPLACE VIEW mart_plan AS
        SELECT p.sub_id, p.offer_id, p.holdout, DATE '{SCORE_DATE}' AS month_start,
               s.p_redeem, s.value, s.cost, s.cost_face, s.net,
               g.segment_id, g.segment, g.stage, g.var_band,
               d.division, d.area_type, d.handset_tier, d.is_smartphone
        FROM ml_plan p JOIN ml_offer_scores s USING (sub_id, offer_id)
        JOIN ml_segments g USING (sub_id) JOIN dim_subscriber d USING (sub_id)""")
    seg_mix = con.execute("""SELECT segment_id, segment, offer_id, COUNT(*) AS subs, SUM(cost) AS spend, SUM(net) AS net
                             FROM mart_plan WHERE NOT holdout GROUP BY ALL ORDER BY 1, 3""").df()
    seg_size = con.execute("SELECT segment_id, COUNT(*) AS base FROM ml_segments GROUP BY 1").df()
    con.close()

    readout.to_csv(out / "pilot_readout.csv", index=False)
    um.calibration.round(4).to_csv(out / "uplift_blp_tests.csv", index=False)
    um.chosen.round(4).to_csv(out / "uplift_chosen.csv", index=False)
    fr.round(2).to_csv(out / "frontier_model.csv", index=False)
    ht.round(4).to_csv(out / "holdout_power.csv", index=False)
    seg_mix.to_csv(out / "plan_by_segment.csv", index=False)

    summary = {
        "operator_scale": scale, "budget_operator_bdt": bc["quarterly_bdt"], "best_single_offer": best_offer,
        "plans_operator": {k: {"targeted": v["targeted"] * scale, "spend_bdt": v["spend"] * scale,
                               "spend_face_bdt": v["spend_face"] * scale, "expected_net_margin_bdt": v["net"] * scale,
                               "roi": v["net"] / v["spend"] if v["spend"] else None}
                           for k, v in values.items()},
        "max_profitable_spend_operator_bdt": float(steps.cum_cost.iloc[-1]) * scale if len(steps) else 0.0,
        "max_net_operator_bdt": float(steps.cum_net.iloc[-1]) * scale if len(steps) else 0.0,
        "pilot_ipw_net_per_pilot_sub": ipw,
        "plan_offer_mix": plan[~plan.holdout].offer_id.value_counts().to_dict(),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=float), encoding="utf-8")
    _charts(out, readout, fr, seg_mix, seg_size, ht, scale, bc, gross_per)
    _write_md(out, summary, readout, um, ht, seg_mix, seg_size, scale, bc)
    return summary


def _charts(out, readout, fr, seg_mix, seg_size, ht, scale, bc, gross_per):
    # 1. pilot readout
    r = readout.iloc[::-1]
    fig, ax = plt.subplots(figsize=(10, 4.4))
    ys = np.arange(len(r))
    ax.barh(ys + 0.2, r.margin_uplift_90d, 0.38, xerr=1.96 * r.margin_uplift_se, color="#99d5cf",
            ecolor=MUTED, capsize=3, label="Extra 90-day margin per targeted sub (95% CI)")
    ax.barh(ys - 0.2, r.net_per_targeted_economic, 0.38,
            color=[ACCENT if v > 0 else "#b91c1c" for v in r.net_per_targeted_economic],
            label="Net of offer cost (network-cost view)")
    ax.scatter(r.net_per_targeted_face, ys - 0.2, marker="|", s=200, color="#111827", zorder=5,
               label="Net of cost at face value")
    ax.axvline(0, color=MUTED, lw=0.8)
    ax.set_yticks(ys, r.offer)
    ax.set_xlabel("৳ per targeted subscriber (Jan-2026 randomised pilot, 8,000 per arm)", color=MUTED, fontsize=8)
    ax.legend(fontsize=7.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.grid(axis="y", visible=False)
    style(ax, "What the pilot proved: cashback and bonus data pay; bundle discount loses money",
          "Retention moved <1pp for every offer; the measurable payoff is extra spend")
    footer(fig)
    fig.tight_layout()
    fig.savefig(out / "pilot_readout.png", dpi=160)
    plt.close(fig)

    # 2. frontier (model)
    fig, ax = plt.subplots(figsize=(9, 4.8))
    x = fr.budget_operator / 1e7
    ax.plot(x, fr.optimised * scale / 1e7, color=ACCENT, lw=2.4, label="Optimised (uplift x cost)")
    ax.plot(x, fr.blanket * scale / 1e7, color=MUTED, lw=1.4, ls="--", label="Blanket: winning offer, random order")
    ax.plot(x, fr.highest_churn_risk * scale / 1e7, color=ACCENT2, lw=1.4, ls=":", label="Winning offer to highest churn risk")
    ax.axvline(bc["quarterly_bdt"] / 1e7, color="#d1d5db", lw=1)
    ax.text(bc["quarterly_bdt"] / 1e7 + 0.05, ax.get_ylim()[1] * 0.05, "৳1 crore", color=MUTED, fontsize=8)
    ax.set_xlabel("Quarterly budget (৳ crore, operator scale)", color=MUTED, fontsize=8)
    ax.set_ylabel("Expected 12-month incremental margin, net of cost (৳ crore)", color=MUTED, fontsize=8)
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    style(ax, "Spend where the uplift is, not where the risk is", "Model estimates from pilot-trained uplift models")
    footer(fig)
    fig.tight_layout()
    fig.savefig(out / "frontier_model.png", dpi=160)
    plt.close(fig)

    # 3. plan by segment
    piv = seg_mix.pivot_table(index=["segment_id", "segment"], columns="offer_id", values="subs", aggfunc="sum").fillna(0)
    piv = piv.reindex(pd.MultiIndex.from_frame(seg_size.merge(seg_mix[["segment_id", "segment"]].drop_duplicates(),
                                                              on="segment_id", how="left")
                                               .fillna({"segment": ""})[["segment_id", "segment"]]
                                               .sort_values("segment_id"))).fillna(0)
    base = seg_size.set_index("segment_id").base
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ys = np.arange(len(piv))[::-1]
    left = np.zeros(len(piv))
    for o in [c for c in OFFER_COLOR if c in piv.columns]:
        share = piv[o].to_numpy() / base.reindex(piv.index.get_level_values(0)).to_numpy() * 100
        ax.barh(ys, share, left=left, color=OFFER_COLOR[o], label=LABEL[o])
        left += share
    for y, v in zip(ys, left):
        ax.text(v + 0.5, y, f"{v:.0f}%", va="center", fontsize=8, color="#374151")
    names = [f"{i}. {n}" if n else str(i) for i, n in piv.index]
    ax.set_yticks(ys, names)
    ax.set_xlabel("% of segment that receives an offer under the ৳1 crore plan", color=MUTED, fontsize=8)
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.grid(axis="y", visible=False)
    style(ax, "Who gets what under the ৳1 crore plan", "Optimiser output; segments from Phase 4")
    footer(fig)
    fig.tight_layout()
    fig.savefig(out / "plan_by_segment.png", dpi=160)
    plt.close(fig)

    # 4. power
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.plot(ht.holdout_share * 100, ht.mde_margin_bdt_per_sub, color=ACCENT, marker="o", label="Minimum detectable effect")
    ax.axhline(gross_per, color=ACCENT2, ls="--", lw=1.2, label=f"Expected effect (৳{gross_per:.0f} per treated sub)")
    ax.set_xlabel("Holdout share of targeted list (%)", color=MUTED, fontsize=8)
    ax.set_ylabel("৳ per subscriber, 90-day margin", color=MUTED, fontsize=8)
    ax.legend(fontsize=8, frameon=False)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    style(ax, "How big a holdout do we need to prove it?", "80% power, 5% two-sided, operator-scale list sizes")
    footer(fig)
    fig.tight_layout()
    fig.savefig(out / "holdout_power.png", dpi=160)
    plt.close(fig)


def _write_md(out, s, readout, um, ht, seg_mix, seg_size, scale, bc):
    p = s["plans_operator"]
    lines = [
        "# Phase 5: offer engine and budget allocation (synthetic data)", "",
        f"Operator scale: our base is a 1% sample; ৳ and subscriber counts are x{scale} (DECISIONS B5.1).", "",
        "## 1. What the randomised pilot proved (Jan 2026, 8,000 per arm)", "",
        "| Offer | Extra 90-day margin / targeted sub | Retention uplift | Redemption | Cost / targeted (network) | Net (network) | Net (face value) | Personalised by |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
        *[f"| {r.offer} | ৳{r.margin_uplift_90d:.1f} ± {1.96 * r.margin_uplift_se:.1f} | {r.retention_uplift_pp:+.1f} ± "
          f"{1.96 * r.retention_uplift_se_pp:.1f} pp | {r.redemption_rate:.0%} | ৳{r.cost_per_targeted_economic:.1f} | "
          f"৳{r.net_per_targeted_economic:+.1f} | ৳{r.net_per_targeted_face:+.1f} | {r.personalised_by} |"
          for r in readout.itertuples()], "",
        "## 2. The ৳1 crore plan vs the alternatives (model estimates, operator scale)", "",
        "| Plan | Subscribers targeted | Spend (network cost) | Spend (face value) | Expected net 12m margin | Net per ৳ spent |",
        "|---|---:|---:|---:|---:|---:|",
        *[f"| {name} | {v['targeted']:,.0f} | ৳{crore(v['spend_bdt']):.2f} cr | ৳{crore(v['spend_face_bdt']):.2f} cr | "
          f"৳{crore(v['expected_net_margin_bdt']):.2f} cr | {v['roi']:.2f} |" if v["roi"] is not None else
          f"| {name} | 0 | ৳0 | ৳0 | ৳0 | - |"
          for name, v in [("Optimised", p["optimised"]), (f"Blanket {s['best_single_offer']}", p["blanket"]),
                          (f"{s['best_single_offer']} to highest churn risk", p["highest_churn_risk"])]], "",
        f"- The most that can be spent profitably is ৳{crore(s['max_profitable_spend_operator_bdt']):.1f} crore a quarter "
        f"(expected net ৳{crore(s['max_net_operator_bdt']):.1f} crore). At ৳1 crore, the budget binds and ranking matters.",
        f"- Offer mix in the plan (sample counts, excluding holdout): {s['plan_offer_mix']}.",
        "- **Pilot check (observable, inverse-propensity weighted):** "
        + "; ".join(f"{k}: ৳{v['net_inc_per_sub']:.2f} ± {1.96 * v['se']:.2f} net 90-day margin per pilot subscriber"
                    for k, v in s["pilot_ipw_net_per_pilot_sub"].items())
        + f". Only {len(seg_mix) and s['plans_operator']['optimised']['targeted'] / (seg_size.base.sum() * scale):.0%} "
          "of subscribers are treated at this budget, so the pilot's 95% intervals overlap and it cannot separate "
          "the policies. That is why the plan launches with its own randomised holdout.", "",
        "## 3. How we prove it worked: holdout and power", "",
        "| Holdout | Holdout subs | MDE margin (৳/sub) | Power at expected effect | MDE retention (pp) | Forgone net margin |",
        "|---:|---:|---:|---:|---:|---:|",
        *[f"| {r.holdout_share:.0%} | {r.holdout_subscribers:,} | ৳{r.mde_margin_bdt_per_sub:.2f} | {r.power_margin:.0%} | "
          f"{r.mde_retention_pp:.2f} | ৳{r.forgone_net_margin_bdt / 1e5:,.1f} lakh |" for r in ht.itertuples()], "",
        "## 4. Uplift model selection (held-out BLP test per offer and outcome)", "",
        um.chosen[["offer_id", "outcome", "ate", "ate_se", "candidate", "ate_shrunk", "beta2_used", "beta2_t"]]
        .round(3).to_string(index=False),
    ]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
