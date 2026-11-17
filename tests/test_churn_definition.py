"""Unit test of the configurable churn/dormancy derivation on a hand-built event history."""
import datetime as dt

import pandas as pd

from nodi.simulate.calendar import build_calendar
from nodi.simulate.churn import derive_inactivity


def test_spells_on_toy_history(tmp_path):
    cfg = {"simulation": {"start_date": "2025-01-01", "observed_months": 6, "burn_in_days": 0,
                          "future_days": 0, "price_shock_date": "2025-07-01", "price_shock_days": 1},
           "churn": {"churn_days": 90, "dormant_days": 30}}
    cal = build_calendar(cfg)  # window 2025-01-01 .. 2025-06-30
    d = dt.date
    (tmp_path / "recharges" / "month=x").mkdir(parents=True)
    pd.DataFrame({
        "sub_id": [1, 1, 1, 2, 3],
        "recharge_date": [d(2025, 1, 1), d(2025, 1, 20), d(2025, 5, 1), d(2025, 1, 5), d(2025, 6, 25)],
    }).to_parquet(tmp_path / "recharges" / "month=x" / "part-0.parquet")
    pd.DataFrame({
        "sub_id": [1, 2, 3], "activation_date": [d(2020, 1, 1)] * 3,
        "last_revenue_date_pre_window": [None, None, d(2024, 12, 1)],
    }).to_parquet(tmp_path / "subscribers.parquet")

    s = derive_inactivity(tmp_path, cfg, cal).set_index(["sub_id", "last_revenue_date"])
    # sub 1: silent 2025-01-21..2025-04-30 = 100 days -> churned on day 90, then reactivated
    r = s.loc[(1, d(2025, 1, 20))]
    assert r.silent_days == 100 and r.reached_churn and r.reactivated
    assert r.churn_date == d(2025, 4, 20)
    # sub 1 last spell: 2025-05-02..2025-06-30 = 60 days -> dormant, not churned, censored
    r = s.loc[(1, d(2025, 5, 1))]
    assert r.silent_days == 60 and not r.reached_churn and r.censored
    # sub 2: silent from 2025-01-06 to window end (176 days) -> churned, never returns
    r = s.loc[(2, d(2025, 1, 5))]
    assert r.reached_churn and not r.reactivated
    # sub 3: pre-window snapshot 2024-12-01, next event 2025-06-25 -> churned + reactivated
    r = s.loc[(3, d(2024, 12, 1))]
    assert r.reached_churn and r.reactivated and r.churn_date == d(2025, 3, 1)
    # a 19-day gap (sub 1, Jan 1 -> Jan 20) is not a spell
    assert (1, d(2025, 1, 1)) not in s.index
