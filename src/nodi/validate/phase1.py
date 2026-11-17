"""Phase 1 report: does the synthetic universe look like Bangladeshi prepaid, and is the truth planted?

KPI SQL here is provisional; Phase 2 replaces it with governed definitions from metrics.yml.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Bengali glyphs (৳) fall back to Nirmala UI (Windows) / Noto Sans Bengali when installed
plt.rcParams["font.family"] = ["DejaVu Sans", "Nirmala UI", "Noto Sans Bengali"]
import logging  # noqa: E402

logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
import pandas as pd  # noqa: E402

from nodi.simulate.calendar import EID_UL_ADHA, EID_UL_FITR, POHELA_BOISHAKH, build_calendar  # noqa: E402

INK, MUTED, ACCENT, ACCENT2, GRID = "#1f2937", "#6b7280", "#0f766e", "#b45309", "#e5e7eb"


def _style(ax, title, subtitle=None):
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", color=INK, pad=18 if subtitle else 8)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=MUTED)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def _footer(fig):
    fig.text(0.01, 0.01, "Nodi Telecom is fictional. All data is synthetic.", fontsize=7, color=MUTED)


def monthly_kpis(con, raw: str, cfg: dict) -> pd.DataFrame:
    churn_days = cfg["churn"]["churn_days"]
    return con.sql(f"""
    WITH events AS (
        SELECT sub_id, recharge_date AS d, amount_bdt FROM read_parquet('{raw}/recharges/*/*.parquet')
        UNION ALL SELECT sub_id, last_revenue_date_pre_window, 0 FROM read_parquet('{raw}/subscribers.parquet')
            WHERE last_revenue_date_pre_window IS NOT NULL
        UNION ALL SELECT sub_id, activation_date, 0 FROM read_parquet('{raw}/subscribers.parquet')
            WHERE activation_date >= DATE '{cfg['simulation']['start_date']}'
    ),
    months AS (
        SELECT DISTINCT date_trunc('month', recharge_date)::DATE AS m
        FROM read_parquet('{raw}/recharges/*/*.parquet')
    ),
    base AS (
        SELECT m.m, COUNT(DISTINCT e.sub_id) AS active_base
        FROM months m JOIN events e ON e.d < m.m AND e.d >= m.m - INTERVAL {churn_days} DAY
        GROUP BY m.m
    ),
    rev AS (
        SELECT date_trunc('month', recharge_date)::DATE AS m, SUM(amount_bdt) AS gross_recharge,
               COUNT(*) AS n_recharges, COUNT(DISTINCT sub_id) AS recharging_subs
        FROM read_parquet('{raw}/recharges/*/*.parquet') GROUP BY 1
    ),
    churn AS (
        SELECT date_trunc('month', churn_date)::DATE AS m, COUNT(*) AS churners
        FROM read_parquet('{raw}/inactivity_spells.parquet') WHERE churn_date IS NOT NULL GROUP BY 1
    )
    SELECT b.m AS month, b.active_base, r.gross_recharge, r.n_recharges, r.recharging_subs,
           COALESCE(c.churners, 0) AS churners,
           r.gross_recharge / b.active_base AS gross_arpu,
           r.n_recharges / r.recharging_subs AS recharges_per_recharger,
           COALESCE(c.churners, 0) / b.active_base AS churn_rate
    FROM base b JOIN rev r USING (m) LEFT JOIN churn c USING (m)
    ORDER BY 1
    """).df()


def phase1_report(cfg: dict) -> dict:
    raw = Path(cfg["paths"]["raw"]).as_posix()
    truth = Path(cfg["paths"]["truth"]).as_posix()
    out = Path(cfg["paths"]["reports"]) / "phase1"
    out.mkdir(parents=True, exist_ok=True)
    cal = build_calendar(cfg)
    econ = cfg["economics"]
    con = duckdb.connect()

    k = monthly_kpis(con, raw, cfg)
    k["month"] = pd.to_datetime(k["month"])
    steady = k[k["month"] >= pd.Timestamp("2025-04-01")]  # after first churn window

    q = lambda s: con.sql(s).df()  # noqa: E731
    subs = q(f"SELECT handset_tier, COUNT(*) n FROM read_parquet('{raw}/subscribers.parquet') GROUP BY 1")
    smart_share = subs.loc[subs.handset_tier != "feature_phone", "n"].sum() / subs.n.sum()
    rech = q(f"""SELECT amount_bdt, channel, COUNT(*) n, SUM(amount_bdt) v
                 FROM read_parquet('{raw}/recharges/*/*.parquet') GROUP BY 1, 2""")
    med = q(f"SELECT median(amount_bdt) m FROM read_parquet('{raw}/recharges/*/*.parquet')")["m"][0]
    small_share = rech.loc[rech.amount_bdt <= 50, "n"].sum() / rech.n.sum()
    ch_mix = rech.groupby("channel", observed=True)["n"].sum() / rech.n.sum()
    data = q(f"""
        SELECT AVG(gb) AS gb FROM (
          SELECT u.sub_id, date_trunc('month', usage_date) m, SUM(data_mb)/1024 gb
          FROM read_parquet('{raw}/daily_usage/*/*.parquet') u
          JOIN read_parquet('{raw}/subscribers.parquet') s USING (sub_id)
          WHERE s.handset_tier <> 'feature_phone' AND usage_date >= DATE '2026-01-01'
          GROUP BY 1, 2)""")["gb"][0]
    spells = q(f"""SELECT COUNT(*) FILTER (WHERE reached_churn) churn_spells,
                          COUNT(*) FILTER (WHERE reactivated) reactivations
                   FROM read_parquet('{raw}/inactivity_spells.parquet')""")
    react_share = spells.reactivations[0] / max(spells.churn_spells[0], 1)
    exp = q(f"""SELECT campaign_type, offer_id, COUNT(*) n, AVG(redeemed::INT) redeem
                FROM read_parquet('{raw}/offer_exposures.parquet') GROUP BY 1, 2 ORDER BY 1, 2""")

    groups = q(f"""SELECT offer_id, response_group, COUNT(*) n
                   FROM read_parquet('{truth}/treatment_truth.parquet') GROUP BY 1, 2""")
    clv = q(f"""SELECT COUNT(*) FILTER (WHERE alive_at_end) alive,
                       SUM(true_clv_margin_12m) total_clv,
                       quantile_cont(true_clv_margin_12m, 0.5) FILTER (WHERE alive_at_end) med_clv,
                       quantile_cont(true_clv_margin_12m, 0.9) FILTER (WHERE alive_at_end) p90_clv,
                       AVG(true_p_churn_90d) FILTER (WHERE alive_at_end) p_churn
                FROM read_parquet('{truth}/clv_truth.parquet')""")

    headline = {
        "subscribers_total": int(subs.n.sum()),
        "active_base_end": int(k["active_base"].iloc[-1]),
        "gross_arpu_bdt_month": float(steady["gross_arpu"].mean()),
        "net_arpu_bdt_month": float(steady["gross_arpu"].mean() * econ["net_revenue_ratio"]),
        "recharges_per_recharger_month": float(steady["recharges_per_recharger"].mean()),
        "median_recharge_bdt": float(med),
        "share_recharges_le_50": float(small_share),
        "monthly_churn_rate": float(steady["churn_rate"].mean()),
        "smartphone_share": float(smart_share),
        "data_gb_per_smartphone_user_month": float(data),
        "churned_spells_reactivated": float(react_share),
        "mfs_share_of_recharges": float(ch_mix.get("mfs", 0)),
        "truth_alive_at_end": int(clv.alive[0]),
        "truth_median_clv_margin_12m": float(clv.med_clv[0]),
        "truth_p90_clv_margin_12m": float(clv.p90_clv[0]),
        "truth_mean_p_churn_90d": float(clv.p_churn[0]),
    }

    # ---------------- charts
    daily = q(f"""SELECT recharge_date d, SUM(amount_bdt) v FROM read_parquet('{raw}/recharges/*/*.parquet')
                  GROUP BY 1 ORDER BY 1""")
    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.plot(pd.to_datetime(daily.d), daily.v / 1e5, color=ACCENT, lw=0.9)
    lo, hi = pd.to_datetime(daily.d).min(), pd.to_datetime(daily.d).max()
    for lst, lab, col in [(EID_UL_FITR, "Eid-ul-Fitr", ACCENT2), (EID_UL_ADHA, "Eid-ul-Adha", MUTED),
                          (POHELA_BOISHAKH, "Pohela Boishakh", "#9ca3af")]:
        for s in lst:
            t = pd.Timestamp(s)
            if lo <= t <= hi:
                ax.axvline(t, color=col, ls="--", lw=0.8)
                ax.text(t, ax.get_ylim()[1] * 0.97, f" {lab}", color=col, fontsize=7, va="top", rotation=90)
    ax.set_ylabel("৳ lakh / day", color=MUTED, fontsize=8)
    _style(ax, "Recharge value spikes in the week before each Eid",
           "Daily gross recharge, all subscribers")
    _footer(fig)
    fig.tight_layout()
    fig.savefig(out / "daily_recharge_festivals.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 4.2))
    x = pd.to_datetime(k.month)
    ax.bar(x, k.active_base / 1000, width=20, color="#99d5cf")
    ax.set_ylabel("Active base ('000, 90-day)", color=MUTED, fontsize=8)
    ax2 = ax.twinx()
    ax2.plot(x, k.churn_rate * 100, color=ACCENT2, marker="o", lw=1.5)
    ax2.set_ylabel("Monthly churn %", color=ACCENT2, fontsize=8)
    ax2.set_ylim(0, max(6, k.churn_rate.max() * 120))
    ax2.spines["top"].set_visible(False)
    ax2.tick_params(colors=MUTED, labelsize=8)
    _style(ax, "Active base and monthly churn (90 days without a revenue event)",
           "A churner is counted in the month they reach 90 silent days. "
           "The Oct-Nov bump is the July tariff shock arriving ~3 months later")
    _footer(fig)
    fig.tight_layout()
    fig.savefig(out / "active_base_churn.png", dpi=160)
    plt.close(fig)

    by_amt = rech.groupby("amount_bdt")["n"].sum()
    by_amt = by_amt[by_amt / by_amt.sum() > 0.003]
    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.bar([f"৳{a}" for a in by_amt.index], by_amt / by_amt.sum() * 100, color=ACCENT)
    ax.set_ylabel("% of recharges", color=MUTED, fontsize=8)
    _style(ax, f"Small, frequent top-ups: {small_share:.0%} of recharges are ৳50 or less",
           f"Median recharge ৳{med:.0f}. Odd amounts are packs bought directly via MFS/app. "
           f"Channel mix: retailer {ch_mix.get('retailer', 0):.0%}, MFS {ch_mix.get('mfs', 0):.0%}, "
           f"app {ch_mix.get('app', 0):.0%}")
    _footer(fig)
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
    _style(ax, "PLANTED TRUTH: who responds to which offer (next quarter)",
           "Hidden from all models. Used only to validate uplift models in Phase 5")
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    _footer(fig)
    fig.tight_layout()
    fig.savefig(out / "truth_response_groups.png", dpi=160)
    plt.close(fig)

    # ---------------- summary markdown
    lines = ["# Phase 1 summary (synthetic data)", "", "## Headline numbers", ""]
    lines += [f"- **{key}**: {val:,.3f}" if isinstance(val, float) else f"- **{key}**: {val:,}"
              for key, val in headline.items()]
    lines += ["", "## Monthly KPIs (provisional SQL; governed versions arrive in Phase 2)", "",
              k.to_markdown(index=False, floatfmt=".3f") if _has_tabulate() else k.to_string(index=False),
              "", "## Offer exposures", "", exp.to_string(index=False),
              "", "## Planted response groups (share by offer)", "", share.round(1).to_string()]
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    k.to_csv(out / "monthly_kpis.csv", index=False)
    return headline


def _has_tabulate() -> bool:
    try:
        import tabulate  # noqa: F401
        return True
    except ImportError:
        return False
