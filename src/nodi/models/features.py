"""Point-in-time feature snapshots and churn labels.

Every feature for snapshot date T uses only events strictly before T. The label looks forward:

    churn_90d = the subscriber goes silent within [T, T+90) and stays silent for >= churn_days
              (i.e. a churn spell whose last revenue event is before T+90 and whose churn date is >= T)

This matches how the pilot outcome is measured (mart_pilot_outcome) and needs data up to T+180,
so the latest labelled snapshot is 2026-01-01.
"""
from __future__ import annotations

import datetime as dt

import duckdb
import pandas as pd

CATEGORICAL = ["division", "area_type", "handset_tier", "acquisition_channel"]
NUMERIC = [
    "tenure_months", "days_since_last_event", "rech_30", "rech_prev30", "rech_90", "rech_180",
    "rech_trend", "gross_30", "gross_90", "avg_recharge_90", "max_gap_90", "mfs_share_90",
    "app_share_90", "active_days_30", "active_days_prev30", "data_mb_30", "data_mb_prev30",
    "data_trend", "voice_30", "voice_prev30", "voice_trend", "n_packs_90", "pack_spend_90",
    "data_pack_share_90", "days_to_pack_expiry", "n_offers_90", "offer_redeemed_90",
    "dormant_spells_365", "ever_reactivated", "dual_sim_handset", "is_smartphone",
]
FEATURES = NUMERIC + CATEGORICAL


def snapshot_sql(T: dt.date, with_label: bool) -> str:
    t = f"DATE '{T}'"
    label = ""
    if with_label:
        label = f""",
        EXISTS (SELECT 1 FROM fct_inactivity_spell s
                WHERE s.sub_id = pop.sub_id AND s.reached_churn
                  AND s.churn_date >= {t} AND s.last_revenue_date < {t} + INTERVAL 90 DAY)::INT AS churn_90d"""
    return f"""
    WITH pop AS (   -- 90-day revenue-active at T (same rule as metrics.yml active_base)
        SELECT d.* FROM dim_subscriber d
        WHERE d.first_event_date < {t}
          AND NOT EXISTS (SELECT 1 FROM fct_inactivity_spell s
                          WHERE s.sub_id = d.sub_id AND s.churn_date < {t}
                            AND (s.return_date IS NULL OR s.return_date >= {t}))
    ),
    ev AS (SELECT sub_id, MAX(date) AS last_event FROM v_revenue_event WHERE date < {t} GROUP BY 1),
    r AS (
        SELECT sub_id,
            COUNT(*) FILTER (WHERE date >= {t} - INTERVAL 30 DAY) AS rech_30,
            COUNT(*) FILTER (WHERE date >= {t} - INTERVAL 60 DAY AND date < {t} - INTERVAL 30 DAY) AS rech_prev30,
            COUNT(*) FILTER (WHERE date >= {t} - INTERVAL 90 DAY) AS rech_90,
            COUNT(*) AS rech_180,
            SUM(gross_bdt) FILTER (WHERE date >= {t} - INTERVAL 30 DAY) AS gross_30,
            SUM(gross_bdt) FILTER (WHERE date >= {t} - INTERVAL 90 DAY) AS gross_90,
            AVG(gross_bdt) FILTER (WHERE date >= {t} - INTERVAL 90 DAY) AS avg_recharge_90,
            AVG((channel = 'mfs')::INT) FILTER (WHERE date >= {t} - INTERVAL 90 DAY) AS mfs_share_90,
            AVG((channel = 'app')::INT) FILTER (WHERE date >= {t} - INTERVAL 90 DAY) AS app_share_90
        FROM fct_recharge WHERE date < {t} AND date >= {t} - INTERVAL 180 DAY GROUP BY 1
    ),
    gaps AS (
        SELECT sub_id, MAX(g) AS max_gap_90 FROM (
            SELECT sub_id, datediff('day', date, LEAD(date, 1, {t}) OVER (PARTITION BY sub_id ORDER BY date)) AS g
            FROM fct_recharge WHERE date < {t} AND date >= {t} - INTERVAL 90 DAY) GROUP BY 1
    ),
    u AS (
        SELECT sub_id,
            COUNT(*) FILTER (WHERE date >= {t} - INTERVAL 30 DAY) AS active_days_30,
            COUNT(*) FILTER (WHERE date < {t} - INTERVAL 30 DAY) AS active_days_prev30,
            SUM(data_mb) FILTER (WHERE date >= {t} - INTERVAL 30 DAY) AS data_mb_30,
            SUM(data_mb) FILTER (WHERE date < {t} - INTERVAL 30 DAY) AS data_mb_prev30,
            SUM(voice_min) FILTER (WHERE date >= {t} - INTERVAL 30 DAY) AS voice_30,
            SUM(voice_min) FILTER (WHERE date < {t} - INTERVAL 30 DAY) AS voice_prev30
        FROM fct_daily_usage WHERE date < {t} AND date >= {t} - INTERVAL 60 DAY GROUP BY 1
    ),
    p AS (
        SELECT pp.sub_id, COUNT(*) AS n_packs_90, SUM(pp.price_bdt) AS pack_spend_90,
               AVG((dp.pack_type <> 'voice')::INT) AS data_pack_share_90,
               MAX(pp.date + dp.validity_days::INTEGER) AS pack_valid_until
        FROM fct_pack_purchase pp JOIN dim_pack dp USING (pack_id)
        WHERE pp.date < {t} AND pp.date >= {t} - INTERVAL 90 DAY GROUP BY 1
    ),
    o AS (
        SELECT sub_id, COUNT(*) AS n_offers_90, MAX(redeemed::INT) AS offer_redeemed_90
        FROM fct_offer_exposure
        WHERE offer_id <> 'none' AND date < {t} AND date >= {t} - INTERVAL 90 DAY GROUP BY 1
    ),
    sp AS (
        SELECT sub_id,
            COUNT(*) FILTER (WHERE dormant_date < {t} AND dormant_date >= {t} - INTERVAL 365 DAY) AS dormant_spells_365,
            MAX((reactivated AND return_date < {t})::INT) AS ever_reactivated
        FROM fct_inactivity_spell WHERE last_revenue_date < {t} GROUP BY 1
    )
    SELECT pop.sub_id, {t} AS snapshot_date,
        datediff('month', pop.activation_date, {t}) AS tenure_months,
        datediff('day', ev.last_event, {t}) AS days_since_last_event,
        COALESCE(r.rech_30, 0) AS rech_30, COALESCE(r.rech_prev30, 0) AS rech_prev30,
        COALESCE(r.rech_90, 0) AS rech_90, COALESCE(r.rech_180, 0) AS rech_180,
        (COALESCE(r.rech_30, 0) + 1.0) / (COALESCE(r.rech_prev30, 0) + 1.0) AS rech_trend,
        COALESCE(r.gross_30, 0) AS gross_30, COALESCE(r.gross_90, 0) AS gross_90,
        r.avg_recharge_90, COALESCE(gaps.max_gap_90, 90) AS max_gap_90,
        r.mfs_share_90, r.app_share_90,
        COALESCE(u.active_days_30, 0) AS active_days_30, COALESCE(u.active_days_prev30, 0) AS active_days_prev30,
        COALESCE(u.data_mb_30, 0) AS data_mb_30, COALESCE(u.data_mb_prev30, 0) AS data_mb_prev30,
        (COALESCE(u.data_mb_30, 0) + 50) / (COALESCE(u.data_mb_prev30, 0) + 50) AS data_trend,
        COALESCE(u.voice_30, 0) AS voice_30, COALESCE(u.voice_prev30, 0) AS voice_prev30,
        (COALESCE(u.voice_30, 0) + 10) / (COALESCE(u.voice_prev30, 0) + 10) AS voice_trend,
        COALESCE(p.n_packs_90, 0) AS n_packs_90, COALESCE(p.pack_spend_90, 0) AS pack_spend_90,
        p.data_pack_share_90,
        COALESCE(datediff('day', {t}, p.pack_valid_until), -1) AS days_to_pack_expiry,
        COALESCE(o.n_offers_90, 0) AS n_offers_90, COALESCE(o.offer_redeemed_90, 0) AS offer_redeemed_90,
        COALESCE(sp.dormant_spells_365, 0) AS dormant_spells_365, COALESCE(sp.ever_reactivated, 0) AS ever_reactivated,
        pop.dual_sim_handset::INT AS dual_sim_handset, pop.is_smartphone::INT AS is_smartphone,
        pop.division, pop.area_type, pop.handset_tier, pop.acquisition_channel
        {label}
    FROM pop
    LEFT JOIN ev USING (sub_id) LEFT JOIN r USING (sub_id) LEFT JOIN gaps USING (sub_id)
    LEFT JOIN u USING (sub_id) LEFT JOIN p USING (sub_id) LEFT JOIN o USING (sub_id)
    LEFT JOIN sp USING (sub_id)
    ORDER BY pop.sub_id
    """


def snapshot(con: duckdb.DuckDBPyConnection, T: dt.date, with_label: bool = True) -> pd.DataFrame:
    df = con.execute(snapshot_sql(T, with_label)).df()
    for c in CATEGORICAL:
        df[c] = df[c].astype("category")
    return df


def snapshots(con, dates: list[dt.date], with_label: bool = True) -> pd.DataFrame:
    df = pd.concat([snapshot(con, T, with_label) for T in dates], ignore_index=True)
    for c in CATEGORICAL:
        df[c] = df[c].astype(str).astype("category")
    return df
