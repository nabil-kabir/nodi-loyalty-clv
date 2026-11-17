"""Derive observable inactivity spells (dormancy and churn) from revenue events.

Definition (configurable in config.yaml):
- A revenue event is a recharge (direct pack purchases arrive as recharges too). Activation and
  the pre-window "last revenue date" snapshot also count, so window edges are handled.
- A subscriber is DORMANT once `dormant_days` pass with no revenue event, and CHURNED once
  `churn_days` pass. Silence is right-censored at the end of the observed window.
- A churned subscriber who recharges again is a reactivation (spell has a return_date).
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from .calendar import Calendar

SPELLS_SQL = """
WITH events AS (
    SELECT sub_id, recharge_date AS d FROM read_parquet('{raw}/recharges/*/*.parquet')
    UNION SELECT sub_id, activation_date FROM read_parquet('{raw}/subscribers.parquet')
        WHERE activation_date >= DATE '{start}'
    UNION SELECT sub_id, last_revenue_date_pre_window FROM read_parquet('{raw}/subscribers.parquet')
        WHERE last_revenue_date_pre_window IS NOT NULL
),
gaps AS (
    SELECT sub_id, d AS last_revenue_date,
           LEAD(d) OVER (PARTITION BY sub_id ORDER BY d) AS return_date
    FROM events
)
SELECT sub_id, last_revenue_date, return_date,
       datediff('day', last_revenue_date, COALESCE(return_date, DATE '{end}')) - 1 AS silent_days,
       return_date IS NULL AS censored,
       last_revenue_date + INTERVAL {dormant} DAY AS dormant_date,
       CASE WHEN datediff('day', last_revenue_date, COALESCE(return_date, DATE '{end}')) - 1 >= {churn}
            THEN CAST(last_revenue_date + INTERVAL {churn} DAY AS DATE) END AS churn_date
FROM gaps
WHERE datediff('day', last_revenue_date, COALESCE(return_date, DATE '{end}')) - 1 >= {dormant}
ORDER BY sub_id, last_revenue_date
"""


def derive_inactivity(raw: Path, cfg: dict, cal: Calendar) -> pd.DataFrame:
    ch = cfg["churn"]
    sql = SPELLS_SQL.format(
        raw=Path(raw).as_posix(), start=cal.start, end=cal.date(cal.n_observed),
        dormant=ch["dormant_days"], churn=ch["churn_days"],
    )
    df = duckdb.sql(sql).df()
    for c in ("last_revenue_date", "return_date", "dormant_date", "churn_date"):
        df[c] = pd.to_datetime(df[c]).dt.date.astype(object).where(df[c].notna(), None)
    df["reached_churn"] = df["churn_date"].notna()
    df["reactivated"] = df["reached_churn"] & ~df["censored"]
    return df
