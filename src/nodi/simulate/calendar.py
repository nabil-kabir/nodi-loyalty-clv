"""Day index <-> date mapping and Bangladeshi seasonal multipliers.

Day 0 is the first observed day. Negative days are burn-in; days >= n_observed are the
hidden future used only for ground truth.

Festival dates are approximate (Bangladesh dates depend on moon sighting, +/-1 day);
see ASSUMPTIONS.md.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np

EID_UL_FITR = ["2024-04-11", "2025-03-31", "2026-03-21", "2027-03-10"]
EID_UL_ADHA = ["2024-06-17", "2025-06-07", "2026-05-27", "2027-05-17"]
POHELA_BOISHAKH = ["2024-04-14", "2025-04-14", "2026-04-14", "2027-04-14"]


def _add_months(d: dt.date, months: int) -> dt.date:
    y, m = divmod(d.month - 1 + months, 12)
    return dt.date(d.year + y, m + 1, 1)


@dataclass
class Calendar:
    start: dt.date
    burn_in: int
    n_observed: int
    n_future: int
    recharge_mult: np.ndarray
    voice_mult: np.ndarray
    data_mult: np.ndarray
    acquisition_mult: np.ndarray
    price_shock: np.ndarray  # bool per day

    @property
    def first_day(self) -> int:
        return -self.burn_in

    @property
    def last_day(self) -> int:  # exclusive
        return self.n_observed + self.n_future

    def idx(self, day: int) -> int:
        return day + self.burn_in

    def date(self, day: int) -> dt.date:
        return self.start + dt.timedelta(days=int(day))

    def day_of(self, date: str | dt.date) -> int:
        if isinstance(date, str):
            date = dt.date.fromisoformat(date)
        return (date - self.start).days

    def epoch_days(self) -> int:
        """Days since 1970-01-01 of day 0 (for Arrow date32)."""
        return (self.start - dt.date(1970, 1, 1)).days

    def month_starts(self, lo: int, hi: int) -> list[int]:
        return [d for d in range(lo, hi) if self.date(d).day == 1]


def build_calendar(cfg: dict) -> Calendar:
    sim = cfg["simulation"]
    start = dt.date.fromisoformat(sim["start_date"])
    end = _add_months(start, sim["observed_months"])
    n_obs = (end - start).days
    burn, fut = sim["burn_in_days"], sim["future_days"]
    days = np.arange(-burn, n_obs + fut)
    dates = [start + dt.timedelta(days=int(d)) for d in days]
    n = len(days)

    rech = np.ones(n)
    voice = np.ones(n)
    data = np.ones(n)
    acq = np.ones(n)

    for i, d in enumerate(dates):
        # salary-week effect (many wages are paid in the first week) and month-end squeeze
        if d.day <= 7:
            rech[i] *= 1.07
        elif d.day >= 25:
            rech[i] *= 0.95
        if d.weekday() == 4:  # Friday: weekly holiday
            rech[i] *= 0.90
            voice[i] *= 1.10

    def bump(dates_list, pre, post, r_pre, r_post, v_post, d_post, a_pre):
        for s in dates_list:
            e = start + dt.timedelta(days=(dt.date.fromisoformat(s) - start).days)
            for i, d in enumerate(dates):
                k = (d - e).days
                if -pre <= k <= -1:
                    ramp = 1 + (r_pre - 1) * (pre + 1 + k) / pre  # rises towards Eid
                    rech[i] *= ramp
                    acq[i] *= a_pre
                elif 0 <= k <= post:
                    rech[i] *= r_post
                    voice[i] *= v_post
                    data[i] *= d_post

    bump(EID_UL_FITR, pre=7, post=2, r_pre=2.0, r_post=0.8, v_post=1.45, d_post=1.25, a_pre=1.6)
    bump(EID_UL_ADHA, pre=5, post=2, r_pre=1.5, r_post=0.85, v_post=1.30, d_post=1.15, a_pre=1.3)
    bump(POHELA_BOISHAKH, pre=1, post=0, r_pre=1.15, r_post=1.2, v_post=1.1, d_post=1.15, a_pre=1.0)

    # steady growth in data consumption (~1% per month)
    data *= 1 + 0.01 * (days / 30.4)

    shock = np.zeros(n, dtype=bool)
    s0 = (dt.date.fromisoformat(sim["price_shock_date"]) - start).days
    shock[(days >= s0) & (days < s0 + sim["price_shock_days"])] = True

    return Calendar(start, burn, n_obs, fut, rech, voice, data, acq, shock)
