"""Experiment design: how to PROVE the plan worked.

Design: from the subscribers the optimiser selects, hold out a random share h who receive nothing.
Success is measured as the difference between targeted and holdout over 90 days.

Power: two-sample difference in means (normal approximation; samples are large).
    MDE = (z_{1-a/2} + z_{power}) * sigma * sqrt(1/n_T + 1/n_H)
sigma comes from the pilot's control arm (90-day contribution margin, and retention).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm


def mde(sigma: float, n_t: float, n_h: float, alpha: float = 0.05, power: float = 0.8) -> float:
    if n_t <= 0 or n_h <= 0:
        return float("nan")
    return (norm.ppf(1 - alpha / 2) + norm.ppf(power)) * sigma * np.sqrt(1 / n_t + 1 / n_h)


def power_at(effect: float, sigma: float, n_t: float, n_h: float, alpha: float = 0.05) -> float:
    if n_t <= 0 or n_h <= 0 or not np.isfinite(effect):
        return float("nan")
    se = sigma * np.sqrt(1 / n_t + 1 / n_h)
    return float(norm.cdf(effect / se - norm.ppf(1 - alpha / 2)))


def holdout_table(n_targeted: int, expected_gross_per_sub: float, expected_net_per_sub: float,
                  sigma_margin: float, sigma_retention: float, expected_ret_pp: float,
                  shares=(0.01, 0.02, 0.05, 0.10, 0.20)) -> pd.DataFrame:
    """Trade-off per holdout share. n_targeted at OPERATOR scale."""
    rows = []
    for h in shares:
        n_h = n_targeted * h
        n_t = n_targeted - n_h
        rows.append({
            "holdout_share": h, "holdout_subscribers": int(n_h), "treated_subscribers": int(n_t),
            "mde_margin_bdt_per_sub": mde(sigma_margin, n_t, n_h),
            "power_margin": power_at(expected_gross_per_sub, sigma_margin, n_t, n_h),
            "mde_retention_pp": mde(sigma_retention, n_t, n_h) * 100,
            "power_retention": power_at(expected_ret_pp / 100, sigma_retention, n_t, n_h),
            "forgone_net_margin_bdt": n_h * expected_net_per_sub,
        })
    return pd.DataFrame(rows)
