"""Data-quality checks on the warehouse.

Each check is a SQL query returning the number of violating rows (0 = pass).
severity: error   -> the build fails
          warning -> reported; investigate before trusting affected metrics
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from nodi.metrics import Metrics
from nodi.simulate import catalog as C


def checks(raw: str, cfg: dict) -> list[dict]:
    allowed = ", ".join(str(v) for v in sorted(set(C.DENOMINATIONS) | set(C.PACK_PRICE)))
    start = cfg["simulation"]["start_date"]
    return [
        # ---------------- uniqueness
        dict(name="dim_subscriber_pk", category="uniqueness", severity="error",
             desc="sub_id is unique in dim_subscriber",
             sql="SELECT COUNT(*) - COUNT(DISTINCT sub_id) FROM dim_subscriber"),
        dict(name="fct_recharge_no_exact_duplicates", category="uniqueness", severity="error",
             desc="No fully duplicated recharge rows (double-loaded files)",
             sql="SELECT COUNT(*) FROM (SELECT * FROM fct_recharge GROUP BY ALL HAVING COUNT(*) > 1)"),
        dict(name="fct_daily_usage_pk", category="uniqueness", severity="error",
             desc="One usage summary per subscriber per day",
             sql="SELECT COUNT(*) FROM (SELECT sub_id, date FROM fct_daily_usage GROUP BY 1, 2 HAVING COUNT(*) > 1)"),
        dict(name="fct_subscriber_month_pk", category="uniqueness", severity="error",
             desc="One snapshot row per subscriber per month",
             sql="SELECT COUNT(*) FROM (SELECT sub_id, month_start FROM fct_subscriber_month GROUP BY 1, 2 HAVING COUNT(*) > 1)"),
        # ---------------- referential integrity
        dict(name="recharge_fk_subscriber", category="referential", severity="error",
             desc="Every recharge belongs to a known subscriber",
             sql="SELECT COUNT(*) FROM fct_recharge r ANTI JOIN dim_subscriber d USING (sub_id)"),
        dict(name="usage_fk_subscriber", category="referential", severity="error",
             desc="Every usage row belongs to a known subscriber",
             sql="SELECT COUNT(*) FROM fct_daily_usage u ANTI JOIN dim_subscriber d USING (sub_id)"),
        dict(name="pack_fk_dim_pack", category="referential", severity="error",
             desc="Every pack purchase is a catalogue pack",
             sql="SELECT COUNT(*) FROM fct_pack_purchase p ANTI JOIN dim_pack d USING (pack_id)"),
        dict(name="exposure_fk_dim_offer", category="referential", severity="error",
             desc="Every offer exposure is a catalogue offer (or 'none' for control)",
             sql="SELECT COUNT(*) FROM fct_offer_exposure e ANTI JOIN dim_offer d USING (offer_id)"),
        dict(name="fact_dates_in_dim_date", category="referential", severity="error",
             desc="All recharge and usage dates exist in dim_date (inside the observed window)",
             sql="""SELECT (SELECT COUNT(*) FROM fct_recharge r ANTI JOIN dim_date d USING (date))
                         + (SELECT COUNT(*) FROM fct_daily_usage u ANTI JOIN dim_date d USING (date))"""),
        # ---------------- completeness
        dict(name="no_null_keys", category="completeness", severity="error",
             desc="No NULL keys or amounts in the facts",
             sql="""SELECT (SELECT COUNT(*) FROM fct_recharge WHERE sub_id IS NULL OR date IS NULL OR gross_bdt IS NULL)
                         + (SELECT COUNT(*) FROM fct_daily_usage WHERE sub_id IS NULL OR date IS NULL)
                         + (SELECT COUNT(*) FROM dim_subscriber WHERE division IS NULL OR handset_tier IS NULL)"""),
        dict(name="every_day_has_recharges", category="completeness", severity="error",
             desc="No missing days of recharge data (a missing file would show up here)",
             sql="SELECT COUNT(*) FROM dim_date d ANTI JOIN (SELECT DISTINCT date FROM fct_recharge) r USING (date)"),
        dict(name="daily_volume_anomaly", category="completeness", severity="warning",
             desc="Daily recharge count outside 60%-170% of its trailing 28-day median (festival days excluded)",
             sql="""WITH d AS (SELECT date, COUNT(*) n FROM fct_recharge GROUP BY 1),
                    w AS (SELECT d.date, d.n, median(d.n) OVER (ORDER BY d.date ROWS BETWEEN 28 PRECEDING AND 1 PRECEDING) med
                          FROM d)
                    SELECT COUNT(*) FROM w JOIN dim_date USING (date)
                    WHERE festival_period IS NULL AND med IS NOT NULL AND (n < 0.6 * med OR n > 1.7 * med)"""),
        # ---------------- validity
        dict(name="recharge_amount_positive", category="validity", severity="error",
             desc="Recharge amounts are positive",
             sql="SELECT COUNT(*) FROM fct_recharge WHERE gross_bdt <= 0"),
        dict(name="recharge_amount_known_denomination", category="validity", severity="warning",
             desc="Recharge amount is a standard denomination or a catalogue pack price",
             sql=f"SELECT COUNT(*) FROM fct_recharge WHERE gross_bdt NOT IN ({allowed})"),
        dict(name="usage_non_negative", category="validity", severity="error",
             desc="Voice minutes, data MB and SMS counts are non-negative",
             sql="SELECT COUNT(*) FROM fct_daily_usage WHERE voice_min < 0 OR data_mb < 0 OR sms_count < 0"),
        dict(name="feature_phone_no_data", category="validity", severity="warning",
             desc="Feature-phone subscribers record no mobile data (handset data or usage feed is wrong otherwise)",
             sql="""SELECT COUNT(*) FROM fct_daily_usage u JOIN dim_subscriber d USING (sub_id)
                    WHERE d.handset_tier = 'feature_phone' AND u.data_mb > 0"""),
        # ---------------- temporal consistency
        dict(name="no_events_before_activation", category="consistency", severity="error",
             desc="No recharge or usage before the SIM was activated",
             sql="""SELECT (SELECT COUNT(*) FROM fct_recharge r JOIN dim_subscriber d USING (sub_id) WHERE r.date < d.activation_date)
                         + (SELECT COUNT(*) FROM fct_daily_usage u JOIN dim_subscriber d USING (sub_id) WHERE u.date < d.activation_date)"""),
        dict(name="direct_pack_has_purchase", category="consistency", severity="error",
             desc="Every direct (MFS/app) pack recharge has a matching pack purchase on the same day at the same price",
             sql="""SELECT COUNT(*) FROM fct_recharge r
                    ANTI JOIN fct_pack_purchase p
                    ON p.sub_id = r.sub_id AND p.date = r.date AND p.price_bdt = r.gross_bdt
                    WHERE r.is_pack_direct"""),
        dict(name="spell_lengths_consistent", category="consistency", severity="error",
             desc="Churn spells are >= churn_days long; dormancy spells >= dormant_days",
             sql=f"""SELECT COUNT(*) FROM fct_inactivity_spell
                     WHERE silent_days < {cfg['churn']['dormant_days']}
                        OR (reached_churn AND silent_days < {cfg['churn']['churn_days']})"""),
        # ---------------- reconciliation
        dict(name="raw_vs_warehouse_rows", category="reconciliation", severity="error",
             desc="Row counts in the warehouse equal the raw files",
             sql=f"""SELECT ABS((SELECT COUNT(*) FROM read_parquet('{raw}/recharges/*/*.parquet')) - (SELECT COUNT(*) FROM fct_recharge))
                         + ABS((SELECT COUNT(*) FROM read_parquet('{raw}/daily_usage/*/*.parquet')) - (SELECT COUNT(*) FROM fct_daily_usage))
                         + ABS((SELECT COUNT(*) FROM read_parquet('{raw}/pack_purchases/*/*.parquet')) - (SELECT COUNT(*) FROM fct_pack_purchase))"""),
        dict(name="raw_vs_warehouse_value", category="reconciliation", severity="error",
             desc="Total gross recharge (৳) in the warehouse equals the raw files",
             sql=f"""SELECT (ABS((SELECT SUM(amount_bdt) FROM read_parquet('{raw}/recharges/*/*.parquet'))
                              - (SELECT SUM(gross_bdt) FROM fct_recharge)) > 0.5)::INT"""),
        dict(name="snapshot_vs_fact_revenue", category="reconciliation", severity="error",
             desc="Monthly snapshot revenue sums to the recharge fact",
             sql="""SELECT (ABS((SELECT SUM(gross_recharge_bdt) FROM fct_subscriber_month)
                              - (SELECT SUM(gross_bdt) FROM fct_recharge)) > 0.5)::INT"""),
        dict(name="active_base_roll_forward", category="reconciliation", severity="error",
             desc="Active base(m+1) = active base(m) - churners(m) + new(m) + reactivated(m), every month",
             sql="""WITH m AS (
                        SELECT month_start,
                               COUNT(*) FILTER (WHERE is_active_start) a, COUNT(*) FILTER (WHERE churned_in_month) c,
                               COUNT(*) FILTER (WHERE is_new_in_month) n, COUNT(*) FILTER (WHERE reactivated_in_month) r
                        FROM fct_subscriber_month GROUP BY 1)
                    SELECT COUNT(*) FROM (
                        SELECT a, LEAD(a) OVER (ORDER BY month_start) nxt, c, n, r FROM m)
                    WHERE nxt IS NOT NULL AND nxt <> a - c + n + r"""),
        dict(name="pilot_arms_balanced", category="experiment", severity="error",
             desc="Randomised pilot arms differ in size by at most 1 subscriber",
             sql="""SELECT (MAX(k) - MIN(k) > 1)::INT FROM
                    (SELECT offer_id, COUNT(*) k FROM fct_offer_exposure WHERE campaign_type = 'pilot' GROUP BY 1)"""),
        dict(name="pilot_pre_period_balance", category="experiment", severity="warning",
             desc="Pilot arms have similar pre-pilot ARPU (max/min ratio < 1.10): randomisation sanity check",
             sql="""WITH p AS (SELECT sub_id, offer_id FROM fct_offer_exposure WHERE campaign_type = 'pilot'),
                    pre AS (SELECT p.offer_id, AVG(COALESCE(s.net_revenue_bdt, 0)) v FROM p
                            LEFT JOIN fct_subscriber_month s ON s.sub_id = p.sub_id AND s.month_start = DATE '2025-12-01'
                            GROUP BY 1)
                    SELECT (MAX(v) / MIN(v) >= 1.10)::INT FROM pre"""),
    ]


def plausibility(con) -> list[dict]:
    """KPI range checks through the governed metrics layer."""
    m = Metrics(con)
    k = m.many(["arpu", "churn_rate", "recharge_frequency"])
    out = []
    for name, lo, hi, label in [("arpu", 50, 500, "৳50-৳500"), ("churn_rate", 0.005, 0.10, "0.5%-10%"),
                                ("recharge_frequency", 1, 15, "1-15 per month")]:
        bad = int(((k[name] < lo) | (k[name] > hi)).sum())
        out.append(dict(name=f"plausible_{name}", category="plausibility", severity="warning",
                        desc=f"Monthly {name} within {label} (metrics.yml definition)", violations=bad))
    return out


def run_dq(con: duckdb.DuckDBPyConnection, cfg: dict) -> pd.DataFrame:
    raw = Path(cfg["paths"]["raw"]).as_posix()
    rows = []
    for c in checks(raw, cfg):
        v = int(con.execute(c["sql"]).fetchone()[0] or 0)
        rows.append({k: c[k] for k in ("name", "category", "severity", "desc")} | {"violations": v})
    rows += plausibility(con)
    df = pd.DataFrame(rows)
    df["status"] = df["violations"].map(lambda v: "PASS" if v == 0 else None)
    df.loc[df.status.isna(), "status"] = df.loc[df.status.isna(), "severity"].map({"error": "FAIL", "warning": "WARN"})
    return df[["status", "name", "category", "severity", "violations", "desc"]]


def write_dq_report(df: pd.DataFrame, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    n_pass = (df.status == "PASS").sum()
    lines = [
        "# Data quality report (synthetic data)", "",
        f"**{n_pass} of {len(df)} checks pass.** "
        f"{(df.status == 'FAIL').sum()} errors, {(df.status == 'WARN').sum()} warnings. "
        "Errors fail the build; warnings need investigation before the affected metrics are trusted.", "",
        "| Status | Check | Category | Violations | What it guards |",
        "|---|---|---|---:|---|",
    ]
    for r in df.itertuples():
        lines.append(f"| {r.status} | `{r.name}` | {r.category} | {r.violations:,} | {r.desc} |")
    path = out / "dq_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
