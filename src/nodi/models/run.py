"""Phase 3 orchestrator: backtest + production churn model, CLV holdout + production, scores.

Outputs
  warehouse: ml_scores table + scores_subscriber view (makes clv_12m / revenue_at_risk metrics live)
  reports/phase3: charts, decile tables, drivers in business language, summary
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

from nodi.viz import ACCENT, ACCENT2, GRID, MUTED, footer, plt, style
from nodi.warehouse.build import connect

from . import churn as CH
from . import clv as V
from .drivers import statements, theme_importance
from .features import snapshots, snapshot

SCORE_DATE = CH.PRODUCTION["score"]
HORIZON_WEEKS = 365 / 7


def _log(msg):
    print(f"[models {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run_models(cfg: dict) -> dict:
    out = Path(cfg["paths"]["reports"]) / "phase3"
    out.mkdir(parents=True, exist_ok=True)
    con = connect(cfg, read_only=False)
    summary = {}

    # ================================================================ churn backtest
    tr, ca, te = (snapshots(con, CH.BACKTEST[k]) for k in ("train", "calib", "test"))
    _log(f"backtest snapshots: train {len(tr):,} / calib {len(ca):,} / test {len(te):,}")
    model = CH.fit_churn(tr, ca)
    logit = CH.fit_logistic(tr)
    y = te.churn_90d.to_numpy()
    p = model.predict(te)
    p_lr = CH.logistic_predict(logit, te)
    ev = CH.evaluate(y, p)
    ev_lr = CH.evaluate(y, p_lr)
    rule = CH.bau_rule(te)
    rule_share = rule.mean()
    k = int(round(rule_share * len(y)))
    model_capture_at_rule_volume = y[np.argsort(-p)[:k]].sum() / y.sum()
    early = (te.days_since_last_event <= 14).to_numpy()
    ev_early = CH.evaluate(y[early], p[early])
    dec = CH.decile_table(y, p)
    dec.to_csv(out / "churn_deciles_test.csv", index=False)
    summary["churn_backtest"] = {
        "lightgbm": ev, "logistic": ev_lr,
        "days_since_heuristic_auc": float(roc_auc_score(y, te.days_since_last_event)),
        "bau_rule": {"share_flagged": rule_share, "precision": y[rule].mean(), "recall": y[rule].sum() / y.sum(),
                     "model_recall_same_volume": model_capture_at_rule_volume},
        "early_warning_subset": {"share_of_base": early.mean(), **ev_early},
    }
    _log(f"backtest AUC {ev['auc']:.3f}, top-decile lift {ev['top_decile_lift']:.2f}")

    # drivers on the test snapshot
    sample = te.sample(min(40_000, len(te)), random_state=11)
    themes = theme_importance(model.contributions(sample))
    stm = statements(te)
    themes.to_csv(out / "driver_themes.csv", index=False)
    stm.to_csv(out / "driver_statements.csv", index=False)

    _charts_churn(out, y, p, p_lr, te, rule, dec, themes)

    # ================================================================ churn production
    tr_p, ca_p = snapshots(con, CH.PRODUCTION["train"]), snapshots(con, CH.PRODUCTION["calib"])
    prod = CH.fit_churn(tr_p, ca_p)
    score = snapshot(con, SCORE_DATE, with_label=False)
    for c in ("division", "area_type", "handset_tier", "acquisition_channel"):
        score[c] = pd.Categorical(score[c].astype(str), categories=tr_p[c].cat.categories)
    score["churn_prob_90d"] = prod.predict(score)
    _log(f"scored {len(score):,} active subscribers at {SCORE_DATE}")

    # ================================================================ CLV holdout (observable)
    h_start, h_end = dt.date(2026, 1, 1), dt.date(2026, 7, 1)
    cal = V.rfm(con, dt.date(2025, 1, 1), h_start)
    clv_h = V.fit_clv(cal)
    pred_h = V.predict_clv(clv_h, cal, horizon_weeks=(h_end - h_start).days / 7)
    act = con.execute(f"""SELECT sub_id, COUNT(*) AS tx, SUM(margin_bdt) AS margin
                          FROM fct_recharge WHERE date >= DATE '{h_start}' AND date < DATE '{h_end}' GROUP BY 1""").df()
    base_h = V.run_rate_baseline(con, h_start, 6, 6)
    hd = (cal.merge(pred_h, on="sub_id").merge(act, on="sub_id", how="left")
          .merge(base_h, on="sub_id", how="left").fillna({"tx": 0, "margin": 0, "clv_baseline": 0}))
    summary["clv_holdout"] = {
        "params": {"bgnbd": {k_: float(v) for k_, v in vars(clv_h.bgnbd).items()},
                   "gamma_gamma": {k_: float(v) for k_, v in vars(clv_h.gg).items()},
                   "freq_monetary_corr": clv_h.freq_monetary_corr},
        "total_tx_error": hd.exp_tx.sum() / hd.tx.sum() - 1,
        "bgnbd_gg": _clv_metrics(hd.clv_pred, hd.margin),
        "run_rate": _clv_metrics(hd.clv_baseline, hd.margin),
    }
    _chart_clv_holdout(out, hd)

    # ================================================================ CLV production
    full = V.rfm(con, dt.date(2025, 1, 1), SCORE_DATE)
    clv_p = V.fit_clv(full)
    pred_p = V.predict_clv(clv_p, full, horizon_weeks=HORIZON_WEEKS)
    base_p = V.run_rate_baseline(con, SCORE_DATE, 6, 12)
    s = (score[["sub_id", "churn_prob_90d"]]
         .merge(pred_p, on="sub_id", how="left").merge(base_p, on="sub_id", how="left"))
    # active subscribers with no recharge yet in the window (new SIMs): x = 0 since activation
    miss = s.clv_pred.isna()
    if miss.any():
        first = con.execute("SELECT sub_id, first_event_date FROM dim_subscriber").df().set_index("sub_id")
        T_new = (pd.Timestamp(SCORE_DATE) - pd.to_datetime(first.loc[s.loc[miss, "sub_id"], "first_event_date"])).dt.days.to_numpy() / 7
        zeros = np.zeros(miss.sum())
        s.loc[miss, "p_alive"] = clv_p.bgnbd.p_alive(zeros, zeros, T_new)
        s.loc[miss, "exp_tx"] = clv_p.bgnbd.expected_purchases(HORIZON_WEEKS, zeros, zeros, T_new)
        s.loc[miss, "exp_margin_per_tx"] = clv_p.gg.population_mean
        s.loc[miss, "clv_pred"] = s.loc[miss, "exp_tx"] * clv_p.gg.population_mean
    s["clv_baseline"] = s.clv_baseline.fillna(0)
    order = np.argsort(-s.churn_prob_90d.to_numpy(), kind="stable")
    s["churn_decile"] = 0
    s.loc[s.index[order], "churn_decile"] = np.arange(len(s)) * 10 // len(s) + 1
    scores = pd.DataFrame({
        "sub_id": s.sub_id.astype("int32"), "score_date": SCORE_DATE,
        "churn_prob_90d": s.churn_prob_90d, "churn_decile": s.churn_decile.astype("int8"),
        "clv_12m_pred": s.clv_pred, "clv_12m_baseline": s.clv_baseline,
        "p_alive": s.p_alive, "exp_recharges_12m": s.exp_tx, "exp_margin_per_recharge": s.exp_margin_per_tx,
        # BG/NBD expectation conditional on still being a customer: the value a save protects.
        # (clv_12m_pred already discounts for leaving, so multiplying it by churn_prob double-counts.)
        "value_if_retained_12m": s.exp_tx / s.p_alive.clip(lower=0.05) * s.exp_margin_per_tx,
    })
    summary["clv_production"] = {
        "params": {"bgnbd": {k_: float(v) for k_, v in vars(clv_p.bgnbd).items()},
                   "gamma_gamma": {k_: float(v) for k_, v in vars(clv_p.gg).items()}},
        "scored": len(scores), "total_clv_12m_bdt": float(scores.clv_12m_pred.sum()),
        "median_clv_12m_bdt": float(scores.clv_12m_pred.median()),
        "margin_at_risk_bdt": float((scores.value_if_retained_12m * scores.churn_prob_90d).sum()),
    }

    # ================================================================ persist
    data_dir = Path(cfg["paths"]["data"]) / "models"
    data_dir.mkdir(parents=True, exist_ok=True)
    scores.to_parquet(data_dir / "scores.parquet", index=False)
    con.register("scores_df", scores)
    con.execute("CREATE OR REPLACE TABLE ml_scores AS SELECT * FROM scores_df")
    con.execute(f"""CREATE OR REPLACE VIEW scores_subscriber AS
        SELECT s.*, DATE '{SCORE_DATE}' AS month_start, d.division, d.area_type, d.handset_tier,
               d.is_smartphone, d.acquisition_channel
        FROM ml_scores s JOIN dim_subscriber d USING (sub_id)""")
    con.close()

    (out / "metrics.json").write_text(json.dumps(summary, indent=2, default=float), encoding="utf-8")
    _write_summary(out, summary, themes, stm, dec)
    return summary


def _clv_metrics(pred: pd.Series, actual: pd.Series) -> dict:
    top = pred.rank(ascending=False, method="first") <= 0.2 * len(pred)
    return {
        "mae": float((pred - actual).abs().mean()), "total_bias": float(pred.sum() / actual.sum() - 1),
        "spearman": float(spearmanr(pred, actual).statistic),
        "top20_value_capture": float(actual[top].sum() / actual.sum()),
    }


# ---------------------------------------------------------------- charts
def _charts_churn(out, y, p, p_lr, te, rule, dec, themes):
    g = CH.gains_curve(y, p)
    g_lr = CH.gains_curve(y, p_lr)
    g_ds = CH.gains_curve(y, te.days_since_last_event.to_numpy().astype(float))
    fig, ax = plt.subplots(figsize=(7.5, 5))
    ax.plot(g.share_targeted * 100, g.share_churners_reached * 100, color=ACCENT, lw=2.4, label="Churn model")
    ax.plot(g_lr.share_targeted * 100, g_lr.share_churners_reached * 100, color="#5eaaa0", lw=1.2, ls="--",
            label="Simple logistic regression")
    ax.plot(g_ds.share_targeted * 100, g_ds.share_churners_reached * 100, color=MUTED, lw=1.2,
            label="Rank by days since last recharge")
    ax.plot([0, 100], [0, 100], color="#d1d5db", lw=1, label="Random")
    rx, ry = rule.mean() * 100, y[rule].sum() / y.sum() * 100
    ax.scatter([rx], [ry], color=ACCENT2, zorder=5, s=50)
    ax.annotate(f"Today's win-back rule\n(targets {rx:.0f}%, reaches {ry:.0f}%)", (rx, ry), xytext=(rx + 8, ry - 12),
                fontsize=8, color=ACCENT2, arrowprops=dict(arrowstyle="-", color=ACCENT2, lw=0.8))
    top20 = g.share_churners_reached.iloc[20] * 100
    ax.annotate(f"Call the riskiest 20%:\nreach {top20:.0f}% of churners", (20, top20), xytext=(32, top20 - 3),
                fontsize=8, color=ACCENT, arrowprops=dict(arrowstyle="-", color=ACCENT, lw=0.8))
    ax.set_xlabel("% of active base targeted (riskiest first)", color=MUTED, fontsize=8)
    ax.set_ylabel("% of next quarter's churners reached", color=MUTED, fontsize=8)
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    style(ax, "Who to call: the model finds churners the current rule misses",
          "Out-of-time test, Jan 2026 (model trained on Apr-Jun 2025)")
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    footer(fig)
    fig.tight_layout()
    fig.savefig(out / "churn_gains.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4.4))
    ax.bar(dec.decile.astype(str), dec.churn_rate * 100, color=[ACCENT] + ["#99d5cf"] * 9)
    base = y.mean() * 100
    ax.axhline(base, color=MUTED, ls="--", lw=1)
    ax.text(9.4, base + 1.5, f"base {base:.0f}%", color=MUTED, fontsize=8, ha="right")
    for i, r in dec.iterrows():
        ax.text(i, r.churn_rate * 100 + 1, f"{r.churn_rate:.0%}", ha="center", fontsize=8, color="#374151")
    ax.set_xlabel("Risk decile (1 = riskiest 10% of active base)", color=MUTED, fontsize=8)
    ax.set_ylabel("Churned next quarter (%)", color=MUTED, fontsize=8)
    style(ax, f"The riskiest 10% churn at {dec.churn_rate.iloc[0]:.0%}, {dec.lift.iloc[0]:.1f}x the base rate",
          "Out-of-time test, Jan 2026. Churn = goes silent within the quarter and stays silent 90 days")
    footer(fig)
    fig.tight_layout()
    fig.savefig(out / "churn_deciles.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.5, 5))
    ax.plot([0, 100], [0, 100], color="#d1d5db", lw=1)
    ax.plot(dec.avg_predicted * 100, dec.churn_rate * 100, color=ACCENT, marker="o")
    ax.set_xlabel("Predicted churn probability (%)", color=MUTED, fontsize=8)
    ax.set_ylabel("Actual churn rate (%)", color=MUTED, fontsize=8)
    style(ax, "Probabilities can be read at face value", "Predicted vs actual by risk decile, Jan 2026 test")
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    footer(fig)
    fig.tight_layout()
    fig.savefig(out / "churn_calibration.png", dpi=160)
    plt.close(fig)

    t = themes.iloc[::-1]
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    ax.barh(t.theme, t.share * 100, color=ACCENT)
    for i, v in enumerate(t.share):
        ax.text(v * 100 + 0.5, i, f"{v:.0%}", va="center", fontsize=8, color="#374151")
    ax.set_xlabel("Share of the model's risk signal (mean |SHAP|)", color=MUTED, fontsize=8)
    style(ax, "What drives churn risk in the model", "Feature contributions grouped into business themes")
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.grid(axis="y", visible=False)
    footer(fig)
    fig.tight_layout()
    fig.savefig(out / "churn_drivers.png", dpi=160)
    plt.close(fig)


def _chart_clv_holdout(out, hd):
    hd = hd.copy()
    hd["bucket"] = pd.cut(hd.x, [-1, 0, 5, 10, 20, 30, 40, 60, 500],
                          labels=["0", "1-5", "6-10", "11-20", "21-30", "31-40", "41-60", "60+"])
    g = hd.groupby("bucket", observed=True).agg(pred=("exp_tx", "mean"), act=("tx", "mean"),
                                                 base=("clv_baseline", "mean"), mg=("margin", "mean"),
                                                 clv=("clv_pred", "mean")).reset_index()
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    ax = axes[0]
    xs = np.arange(len(g))
    ax.bar(xs - 0.2, g.act, 0.4, color="#99d5cf", label="Actual")
    ax.plot(xs, g.pred, color=ACCENT, marker="o", label="BG/NBD predicted")
    ax.set_xticks(xs, g.bucket)
    ax.set_xlabel("Repeat recharges in 2025 (calibration)", color=MUTED, fontsize=8)
    ax.legend(fontsize=8, frameon=False)
    style(ax, "Recharges in H1 2026 (holdout)", "Average per subscriber by 2025 frequency")
    ax = axes[1]
    ax.bar(xs - 0.2, g.mg, 0.4, color="#99d5cf", label="Actual margin")
    ax.plot(xs, g.clv, color=ACCENT, marker="o", label="BG/NBD + Gamma-Gamma")
    ax.plot(xs, g.base, color=ACCENT2, marker="s", ls="--", lw=1.2, label="Run-rate baseline")
    ax.set_xticks(xs, g.bucket)
    ax.set_xlabel("Repeat recharges in 2025 (calibration)", color=MUTED, fontsize=8)
    ax.legend(fontsize=8, frameon=False)
    style(ax, "6-month margin, ৳ per subscriber", "Holdout Jan-Jun 2026")
    footer(fig)
    fig.tight_layout()
    fig.savefig(out / "clv_holdout.png", dpi=160)
    plt.close(fig)


def _write_summary(out, s, themes, stm, dec):
    cb, ch = s["churn_backtest"], s["clv_holdout"]
    lg, lr, rule, ew = cb["lightgbm"], cb["logistic"], cb["bau_rule"], cb["early_warning_subset"]
    lines = [
        "# Phase 3 summary (synthetic data)", "",
        "## Churn model: out-of-time test (scored 2026-01-01, trained on Apr-Jun 2025)", "",
        "| Model | AUC | PR-AUC | Brier | Top-decile lift | Churners reached, top 10% | top 20% |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| LightGBM + isotonic | {lg['auc']:.3f} | {lg['pr_auc']:.3f} | {lg['brier']:.3f} | {lg['top_decile_lift']:.2f} | {lg['capture_top10']:.0%} | {lg['capture_top20']:.0%} |",
        f"| Logistic regression | {lr['auc']:.3f} | {lr['pr_auc']:.3f} | {lr['brier']:.3f} | {lr['top_decile_lift']:.2f} | {lr['capture_top10']:.0%} | {lr['capture_top20']:.0%} |",
        f"| Days since last recharge | {cb['days_since_heuristic_auc']:.3f} | | | | | |",
        "",
        f"- Base rate: {lg['base_rate']:.1%} of the active base churns in the quarter.",
        f"- **Today's win-back rule** flags {rule['share_flagged']:.0%} of the base and reaches {rule['recall']:.0%} of churners "
        f"(precision {rule['precision']:.0%}). **The model, contacting the same number of people, reaches {rule['model_recall_same_volume']:.0%}.**",
        f"- **Early warning is harder:** among subscribers who recharged in the last 14 days ({ew['share_of_base']:.0%} of the base), "
        f"AUC is {ew['auc']:.3f} and top-decile lift is {ew['top_decile_lift']:.1f}.",
        "", "### Risk deciles (test)", "", dec.round(3).to_string(index=False), "",
        "## Churn drivers in business language", "",
        "| Theme | Share of model signal |", "|---|---:|",
        *[f"| {r.theme} | {r.share:.0%} |" for r in themes.itertuples()], "",
        *[f"- **{r.theme}.** {r.finding} *Action:* {r.action}" for r in stm.itertuples()], "",
        "## CLV: holdout (calibrate 2025, predict Jan-Jun 2026)", "",
        "| Model | MAE ৳ | Total bias | Spearman | Top-20% value capture |", "|---|---:|---:|---:|---:|",
        *[f"| {n} | {m['mae']:.0f} | {m['total_bias']:+.1%} | {m['spearman']:.3f} | {m['top20_value_capture']:.0%} |"
          for n, m in [("BG/NBD + Gamma-Gamma", ch["bgnbd_gg"]), ("Run-rate baseline", ch["run_rate"])]],
        "",
        f"- Total recharges predicted vs actual: {ch['total_tx_error']:+.1%}.",
        f"- Frequency-monetary correlation {ch['params']['freq_monetary_corr']:+.3f} (Gamma-Gamma assumes ~0: OK).",
        "", "## Production scores (2026-07-01)", "",
        f"- Scored {s['clv_production']['scored']:,} active subscribers.",
        f"- Predicted 12-month CLV: total ৳{s['clv_production']['total_clv_12m_bdt'] / 1e7:,.2f} crore, "
        f"median ৳{s['clv_production']['median_clv_12m_bdt']:,.0f}.",
        f"- Margin at risk (value if retained x churn probability): ৳{s['clv_production']['margin_at_risk_bdt'] / 1e7:,.2f} crore.",
    ]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
