"""Load observable raw data into a DuckDB star schema.

Dimensions : dim_date, dim_subscriber, dim_pack, dim_offer, dim_campaign
Facts      : fct_recharge, fct_pack_purchase, fct_daily_usage, fct_offer_exposure,
             fct_inactivity_spell, fct_subscriber_month (monthly snapshot)
Marts      : mart_subscriber_month, mart_recharge, mart_pilot_outcome (views used by metrics.yml)

Reads data/raw only. Ground truth is never loaded into the warehouse.
"""
from __future__ import annotations

import datetime as dt
import time
from pathlib import Path

import duckdb
import pandas as pd

from nodi.simulate.calendar import EID_UL_ADHA, EID_UL_FITR, POHELA_BOISHAKH, build_calendar
from nodi.simulate.churn import derive_inactivity


def db_path(cfg: dict) -> Path:
    return Path(cfg["paths"]["data"]) / "warehouse.duckdb"


def connect(cfg: dict, read_only: bool = True) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path(cfg)), read_only=read_only)


def _dim_date(cal) -> pd.DataFrame:
    days = pd.date_range(cal.start, cal.date(cal.n_observed - 1), freq="D")
    df = pd.DataFrame({"date": days.date})
    df["year"] = days.year
    df["month"] = days.month
    df["month_start"] = days.to_period("M").start_time.date
    df["day_name"] = days.day_name()
    df["is_friday"] = days.dayofweek == 4
    df["festival_period"] = None
    for name, lst, pre, post in [("eid_ul_fitr", EID_UL_FITR, 7, 2), ("eid_ul_adha", EID_UL_ADHA, 5, 2),
                                 ("pohela_boishakh", POHELA_BOISHAKH, 1, 0)]:
        for s in lst:
            e = dt.date.fromisoformat(s)
            k = (pd.to_datetime(df["date"]) - pd.Timestamp(e)).dt.days
            df.loc[(k >= -pre) & (k < 0), "festival_period"] = f"{name}_pre"
            df.loc[(k >= 0) & (k <= post), "festival_period"] = name
    return df


def build_warehouse(cfg: dict) -> Path:
    t0 = time.time()
    path = db_path(cfg)
    for p in (path, path.with_suffix(".duckdb.wal")):
        if p.exists():
            p.unlink()
    raw = Path(cfg["paths"]["raw"]).as_posix()
    cal = build_calendar(cfg)
    econ = cfg["economics"]
    net, cm = econ["net_revenue_ratio"], econ["contribution_margin_on_net"]
    start, end = cal.start, cal.date(cal.n_observed)  # end is exclusive

    con = duckdb.connect(str(path))
    x = con.execute

    # ---------------- dimensions
    con.register("dim_date_df", _dim_date(cal))
    x("CREATE TABLE dim_date AS SELECT * FROM dim_date_df")
    x(f"CREATE TABLE dim_pack AS SELECT * FROM read_parquet('{raw}/catalog_packs.parquet')")
    x(f"""CREATE TABLE dim_offer AS
          SELECT offer_id, name, nominal_design FROM read_parquet('{raw}/catalog_offers.parquet')
          UNION ALL SELECT 'none', 'No offer (control)', 'Randomised control group: no contact'""")
    x(f"""CREATE TABLE fct_offer_exposure AS
          SELECT sub_id, exposure_date AS date, campaign_id, campaign_type, offer_id, randomised, redeemed
          FROM read_parquet('{raw}/offer_exposures.parquet')""")
    x("""CREATE TABLE dim_campaign AS
         SELECT campaign_id, ANY_VALUE(campaign_type) AS campaign_type, MIN(date) AS start_date,
                BOOL_AND(randomised) AS randomised, COUNT(*) AS subscribers_targeted
         FROM fct_offer_exposure GROUP BY 1""")

    # ---------------- facts
    x(f"""CREATE TABLE fct_recharge AS
          SELECT sub_id, recharge_date AS date, channel::VARCHAR AS channel,
                 amount_bdt AS gross_bdt, amount_bdt * {net} AS net_bdt,
                 amount_bdt * {net} * {cm} AS margin_bdt, is_pack_direct
          FROM read_parquet('{raw}/recharges/*/*.parquet')""")
    x(f"""CREATE TABLE fct_pack_purchase AS
          SELECT sub_id, purchase_date AS date, pack_id::VARCHAR AS pack_id, price_bdt
          FROM read_parquet('{raw}/pack_purchases/*/*.parquet')""")
    x(f"""CREATE TABLE fct_daily_usage AS
          SELECT sub_id, usage_date AS date, voice_min, data_mb, sms_count
          FROM read_parquet('{raw}/daily_usage/*/*.parquet')""")
    x(f"CREATE TABLE stg_subscriber AS SELECT * FROM read_parquet('{raw}/subscribers.parquet')")

    # Inactivity spells are re-derived here so a change to churn.churn_days takes effect
    # without re-simulating.
    con.register("spells_df", derive_inactivity(Path(cfg["paths"]["raw"]), cfg, cal))
    x("CREATE TABLE fct_inactivity_spell AS SELECT * FROM spells_df")

    x(f"""CREATE VIEW v_revenue_event AS
          SELECT sub_id, date FROM fct_recharge
          UNION SELECT sub_id, activation_date FROM stg_subscriber WHERE activation_date >= DATE '{start}'
          UNION SELECT sub_id, last_revenue_date_pre_window FROM stg_subscriber
                WHERE last_revenue_date_pre_window IS NOT NULL""")

    x(f"""CREATE TABLE dim_subscriber AS
          SELECT s.sub_id, s.activation_date, s.division, s.area_type, s.handset_tier,
                 s.handset_tier <> 'feature_phone' AS is_smartphone, s.dual_sim_handset,
                 s.acquisition_channel, s.last_revenue_date_pre_window,
                 f.first_event_date,
                 s.activation_date >= DATE '{start}' AS acquired_in_window
          FROM stg_subscriber s
          LEFT JOIN (SELECT sub_id, MIN(date) AS first_event_date FROM v_revenue_event GROUP BY 1) f
          USING (sub_id)""")
    x("DROP TABLE stg_subscriber")
    x(f"""CREATE OR REPLACE VIEW v_revenue_event AS
          SELECT sub_id, date FROM fct_recharge
          UNION SELECT sub_id, activation_date FROM dim_subscriber WHERE acquired_in_window
          UNION SELECT sub_id, last_revenue_date_pre_window FROM dim_subscriber
                WHERE last_revenue_date_pre_window IS NOT NULL""")

    # ---------------- monthly subscriber snapshot
    x(f"""CREATE TABLE fct_subscriber_month AS
    WITH months AS (SELECT DISTINCT month_start FROM dim_date),
    grid AS (
        SELECT d.sub_id, m.month_start, d.first_event_date, d.activation_date
        FROM dim_subscriber d JOIN months m ON d.first_event_date < m.month_start + INTERVAL 1 MONTH
    ),
    blocked AS (   -- inside a churned spell at the start of the month
        SELECT DISTINCT g.sub_id, g.month_start FROM grid g
        JOIN fct_inactivity_spell s ON s.sub_id = g.sub_id
        WHERE s.churn_date < g.month_start AND (s.return_date IS NULL OR s.return_date >= g.month_start)
    ),
    rech AS (
        SELECT sub_id, date_trunc('month', date)::DATE AS month_start, COUNT(*) AS n_recharges,
               SUM(gross_bdt) AS gross_recharge_bdt, SUM(net_bdt) AS net_revenue_bdt,
               SUM(margin_bdt) AS margin_bdt,
               COUNT(*) FILTER (WHERE channel = 'mfs') AS n_recharges_mfs
        FROM fct_recharge GROUP BY 1, 2
    ),
    usage AS (
        SELECT sub_id, date_trunc('month', date)::DATE AS month_start, COUNT(*) AS active_days,
               SUM(voice_min) AS voice_min, SUM(data_mb) AS data_mb, SUM(sms_count) AS sms_count
        FROM fct_daily_usage GROUP BY 1, 2
    ),
    packs AS (
        SELECT sub_id, date_trunc('month', date)::DATE AS month_start, COUNT(*) AS n_packs,
               SUM(price_bdt) AS pack_spend_bdt
        FROM fct_pack_purchase GROUP BY 1, 2
    ),
    offers AS (
        SELECT sub_id, date_trunc('month', date)::DATE AS month_start, COUNT(*) AS n_offers,
               BOOL_OR(redeemed) AS offer_redeemed
        FROM fct_offer_exposure WHERE offer_id <> 'none' GROUP BY 1, 2
    ),
    ch AS (SELECT sub_id, date_trunc('month', churn_date)::DATE AS month_start, COUNT(*) AS n
           FROM fct_inactivity_spell WHERE churn_date IS NOT NULL GROUP BY 1, 2),
    dm AS (SELECT sub_id, date_trunc('month', dormant_date)::DATE AS month_start, COUNT(*) AS n
           FROM fct_inactivity_spell WHERE dormant_date < DATE '{end}' GROUP BY 1, 2),
    re AS (SELECT sub_id, date_trunc('month', return_date)::DATE AS month_start, COUNT(*) AS n
           FROM fct_inactivity_spell WHERE reactivated GROUP BY 1, 2)
    SELECT g.sub_id, g.month_start,
           datediff('month', g.activation_date, g.month_start) AS tenure_months,
           (g.first_event_date < g.month_start AND b.sub_id IS NULL) AS is_active_start,
           (g.first_event_date >= g.month_start) AS is_new_in_month,
           COALESCE(r.n_recharges, 0) AS n_recharges,
           COALESCE(r.n_recharges, 0) > 0 AS is_paying,
           COALESCE(r.n_recharges_mfs, 0) AS n_recharges_mfs,
           COALESCE(r.gross_recharge_bdt, 0) AS gross_recharge_bdt,
           COALESCE(r.net_revenue_bdt, 0) AS net_revenue_bdt,
           COALESCE(r.margin_bdt, 0) AS margin_bdt,
           COALESCE(u.active_days, 0) AS active_days,
           COALESCE(u.voice_min, 0) AS voice_min,
           COALESCE(u.data_mb, 0) AS data_mb,
           COALESCE(u.sms_count, 0) AS sms_count,
           COALESCE(p.n_packs, 0) AS n_packs,
           COALESCE(p.pack_spend_bdt, 0) AS pack_spend_bdt,
           COALESCE(o.n_offers, 0) AS n_offers,
           COALESCE(o.offer_redeemed, FALSE) AS offer_redeemed,
           ch.n IS NOT NULL AS churned_in_month,
           dm.n IS NOT NULL AS dormant_in_month,
           re.n IS NOT NULL AS reactivated_in_month
    FROM grid g
    LEFT JOIN blocked b USING (sub_id, month_start)
    LEFT JOIN rech r USING (sub_id, month_start)
    LEFT JOIN usage u USING (sub_id, month_start)
    LEFT JOIN packs p USING (sub_id, month_start)
    LEFT JOIN offers o USING (sub_id, month_start)
    LEFT JOIN ch USING (sub_id, month_start)
    LEFT JOIN dm USING (sub_id, month_start)
    LEFT JOIN re USING (sub_id, month_start)
    ORDER BY 2, 1
    """)

    # ---------------- marts (the only tables metrics.yml queries)
    x("""CREATE VIEW mart_subscriber_month AS
         SELECT f.*, d.division, d.area_type, d.handset_tier, d.is_smartphone, d.dual_sim_handset,
                d.acquisition_channel,
                CASE WHEN f.tenure_months < 6 THEN '0-5m' WHEN f.tenure_months < 24 THEN '6-23m'
                     WHEN f.tenure_months < 60 THEN '2-5y' ELSE '5y+' END AS tenure_band
         FROM fct_subscriber_month f JOIN dim_subscriber d USING (sub_id)""")
    x("""CREATE VIEW mart_recharge AS
         SELECT r.*, date_trunc('month', r.date)::DATE AS month_start, d.division, d.area_type,
                d.handset_tier, d.is_smartphone, d.acquisition_channel
         FROM fct_recharge r JOIN dim_subscriber d USING (sub_id)""")
    x("""CREATE VIEW mart_pilot_outcome AS
         WITH p AS (
             SELECT sub_id, date AS pilot_start,
                    CASE WHEN offer_id = 'none' THEN 'control' ELSE offer_id END AS arm, redeemed
             FROM fct_offer_exposure WHERE campaign_type = 'pilot'
         ),
         rev AS (
             SELECT p.sub_id, SUM(r.net_bdt) AS net_revenue_90d, SUM(r.margin_bdt) AS margin_90d,
                    COUNT(r.date) AS recharges_90d
             FROM p LEFT JOIN fct_recharge r
               ON r.sub_id = p.sub_id AND r.date >= p.pilot_start AND r.date < p.pilot_start + INTERVAL 90 DAY
             GROUP BY 1
         ),
         ch AS (   -- went silent before the pilot window ended and stayed silent 90 days
             SELECT DISTINCT p.sub_id FROM p JOIN fct_inactivity_spell s USING (sub_id)
             WHERE s.reached_churn AND s.churn_date >= p.pilot_start
               AND s.last_revenue_date < p.pilot_start + INTERVAL 90 DAY
         )
         SELECT p.sub_id, p.pilot_start, date_trunc('month', p.pilot_start)::DATE AS month_start,
                p.arm, p.redeemed,
                COALESCE(rev.net_revenue_90d, 0) AS net_revenue_90d,
                COALESCE(rev.margin_90d, 0) AS margin_90d,
                COALESCE(rev.recharges_90d, 0) AS recharges_90d,
                ch.sub_id IS NOT NULL AS churned,
                d.division, d.area_type, d.handset_tier, d.is_smartphone, d.acquisition_channel
         FROM p LEFT JOIN rev USING (sub_id) LEFT JOIN ch USING (sub_id)
         JOIN dim_subscriber d USING (sub_id)""")

    con.close()
    print(f"[warehouse] built {path.name} in {time.time() - t0:,.0f}s", flush=True)
    return path
