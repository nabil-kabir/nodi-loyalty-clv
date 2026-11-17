"""Phase 1 report: does the synthetic universe look like Bangladeshi prepaid, and is the truth planted?

All KPIs come from the governed metrics layer (metrics.yml). Ground truth is read only for the
planted-truth section, which is why this report lives in nodi.validate.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from nodi.metrics import Metrics
from nodi.simulate.calendar import EID_UL_ADHA, EID_UL_FITR, POHELA_BOISHAKH
from nodi.viz import ACCENT, ACCENT2, MUTED, GRID, footer, plt, style
from nodi.warehouse.build import connect


def phase1_report(cfg: dict) -> dict:
    truth = Path(cfg["paths"]["truth"]).as_posix()
    out = Path(cfg["paths"]["reports"]) / "phase1"
    out.mkdir(parents=True, exist_ok=True)
    con = connect(cfg)
    m = Metrics(con)

    k = m.many(["active_base", "arpu", "arpu_active_base", "churn_rate", "recharge_frequency",
                "reactivations", "churners"])
    k["month_start"] = pd.to_datetime(k.month_start)
    denom = m.get("recharge_count", by=["gross_bdt"])
    chan = m.get("recharge_count", by=["channel"])
    ch_mix = chan.set_index("channel").recharge_count / chan.recharge_count.sum()
    small_share = denom.loc[denom.gross_bdt <= 50, "recharge_count"].sum() / denom.recharge_count.sum()
    med = con.execute("SELECT median(gross_bdt) FROM mart_recharge").fetchone()[0]
    smart = con.execute("SELECT AVG(is_smartphone::INT) FROM dim_subscriber").fetchone()[0]
    react = con.execute("SELECT AVG(reactivated::INT) FROM fct_inactivity_spell WHERE reached_churn").fetchone()[0]

    q = lambda s: duckdb.sql(s).df()  # noqa: E731  (ground truth only below this line)
    groups = q(f"""SELECT offer_id, response_group, COUNT(*) n
                   FROM read_parquet('{truth}/treatment_truth.parquet') GROUP BY 1, 2""")
    clv = q(f"""SELECT COUNT(*) FILTER (WHERE alive_at_end) alive,
                       quantile_cont(true_clv_margin_12m, 0.5) FILTER (WHERE alive_at_end) med_clv,
                       quantile_cont(true_clv_margin_12m, 0.9) FILTER (WHERE alive_at_end) p90_clv,
                       AVG(true_p_churn_90d) FILTER (WHERE alive_at_end) p_churn
                FROM read_parquet('{truth}/clv_truth.parquet')""")

    headline = {
        "subscribers_total": int(con.execute("SELECT COUNT(*) FROM dim_subscriber").fetchone()[0]),
        "active_base_end": int(k.active_base.iloc[-1]),
        "arpu_paying_net_bdt": float(k.arpu.mean()),
        "arpu_active_net_bdt": float(k.arpu_active_base.mean()),
        "recharges_per_paying_sub_month": float(k.recharge_frequency.mean()),
        "median_recharge_bdt": float(med),
        "share_recharges_le_50": float(small_share),
        "monthly_churn_rate": float(k.churn_rate.mean()),
        "smartphone_share": float(smart),
        "data_gb_per_smartphone_user_month": float(m.get("data_gb_per_smartphone_user", by=[]).iloc[0, 0]),
        "churned_spells_reactivated": float(react),
        "mfs_share_of_recharges": float(ch_mix.get("mfs", 0)),
        "truth_alive_at_end": int(clv.alive[0]),
        "truth_median_clv_margin_12m": float(clv.med_clv[0]),
        "truth_p90_clv_margin_12m": float(clv.p90_clv[0]),
        "truth_mean_p_churn_90d": float(clv.p_churn[0]),
    }

    # ---------------- charts
    daily = m.get("recharge_value", by=["date"])
    d = pd.to_datetime(daily.date)
    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.plot(d, daily.recharge_value / 1e5, color=ACCENT, lw=0.9)
    top = (daily.recharge_value / 1e5).max() * 1.02
    for lst, lab, col in [(EID_UL_FITR, "Eid-ul-Fitr", ACCENT2), (EID_UL_ADHA, "Eid-ul-Adha", MUTED),
                          (POHELA_BOISHAKH, "Pohela Boishakh", "#9ca3af")]:
        for s in lst:
            t = pd.Timestamp(s)
            if d.min() <= t <= d.max():
                ax.axvline(t, color=col, ls="--", lw=0.8)
                ax.text(t, top, f" {lab}", color=col, fontsize=7, va="top", rotation=90)
    ax.set_ylabel("৳ lakh / day", color=MUTED, fontsize=8)
    style(ax, "Recharge value spikes in the week before each Eid", "Daily gross recharge, all subscribers")
    footer(fig)
    fig.tight_layout()
    fig.savefig(out / "daily_recharge_festivals.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.bar(k.month_start, k.active_base / 1000, width=20, color="#99d5cf")
    ax.set_ylabel("Active base ('000, 90-day)", color=MUTED, fontsize=8)
    ax2 = ax.twinx()
    ax2.plot(k.month_start, k.churn_rate * 100, color=ACCENT2, marker="o", lw=1.5)
    ax2.set_ylabel("Monthly churn %", color=ACCENT2, fontsize=8)
    ax2.set_ylim(0, max(6, k.churn_rate.max() * 120))
    ax2.spines["top"].set_visible(False)
    ax2.tick_params(colors=MUTED, labelsize=8)
    style(ax, "Active base and monthly churn (90 days without a revenue event)",
          "A churner is counted in the month they reach 90 silent days. "
          "The Oct-Nov bump is the July tariff shock arriving ~3 months later")
    footer(fig)
    fig.tight_layout()
    fig.savefig(out / "active_base_churn.png", dpi=160)
    plt.close(fig)

    by_amt = denom.set_index("gross_bdt").recharge_count.sort_index()
    by_amt = by_amt[by_amt / by_amt.sum() > 0.003]
    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.bar([f"৳{a:g}" for a in by_amt.index], by_amt / by_amt.sum() * 100, color=ACCENT)
    ax.set_ylabel("% of recharges", color=MUTED, fontsize=8)
    style(ax, f"Small, frequent top-ups: {small_share:.0%} of recharges are ৳50 or less",
          f"Median recharge ৳{med:.0f}. Odd amounts are packs bought directly via MFS/app. "
          f"Channel mix: retailer {ch_mix.get('retailer', 0):.0%}, MFS {ch_mix.get('mfs', 0):.0%}, "
          f"app {ch_mix.get('app', 0):.0%}")
    footer(fig)
    fig.tight_layout()
    fig.savefig(out / "recharge_denominations.png", dpi=160)
    plt.close(fig)

    order = ["persuadable", "sure_thing", "low_responder", "lost_cause", "sleeping_dog"]
    colors = [ACCENT, "#99d5cf", "#d1d5db", "#9ca3af", "#b91c1c"]
    piv = groups.pivot(index="offer_id", columns="response_group", values="n").fillna(0)
    piv = piv.reindex(columns=[c for c in order if c in piv.columns])
    share = piv.div(piv.sum(axis=1), axis=0) * 100
    fig, ax = plt.subplots(figsize=(11, 4.2))
    left = pd.Series(0.0, index=share.index)
    for c, col in zip(share.columns, colors):
        ax.barh(share.index, share[c], left=left, color=col, label=c.replace("_", " "))
        left += share[c]
    ax.set_xlabel("% of subscribers alive at end of window", color=MUTED, fontsize=8)
    ax.legend(ncol=5, fontsize=8, frameon=False, loc="lower center", bbox_to_anchor=(0.5, -0.32))
    style(ax, "PLANTED TRUTH: who responds to which offer (next quarter)",
          "Hidden from all models. Used only to validate uplift models in Phase 5")
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    footer(fig)
    fig.tight_layout()
    fig.savefig(out / "truth_response_groups.png", dpi=160)
    plt.close(fig)
    con.close()

    lines = ["# Phase 1 summary (synthetic data)", "", "KPIs from metrics.yml; truth_* rows from planted ground truth.",
             "", "## Headline numbers", ""]
    lines += [f"- **{key}**: {val:,.3f}" if isinstance(val, float) else f"- **{key}**: {val:,}"
              for key, val in headline.items()]
    lines += ["", "## Monthly KPIs (metrics.yml)", "", k.round(3).to_string(index=False),
              "", "## Planted response groups (share by offer)", "", share.round(1).to_string()]
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    k.round(6).to_csv(out / "monthly_kpis.csv", index=False)
    return headline
