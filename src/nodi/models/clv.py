"""CLV: BG/NBD (Fader, Hardie & Lee 2005) + Gamma-Gamma (Fader, Hardie & Lee 2005b), in scipy.

Why not the `lifetimes` package: unmaintained and not installable on Python 3.14; the two
likelihoods are short, so implementing them keeps dependencies lean and the maths visible.

Transactions are recharge DAYS (a subscriber recharges at most once a day in this data).
Time unit: weeks. Birth = first recharge inside the observation window (existing subscribers are
left-truncated at the window start; see DECISIONS 3.x).
Monetary value = contribution margin per recharge (gross x 0.72 x 0.78, from the warehouse).

Baseline ("run-rate"): average monthly margin over the last 6 months x 12 (what most operators do).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import duckdb
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln, hyp2f1

WEEK = 7.0


def rfm(con: duckdb.DuckDBPyConnection, start: dt.date, end: dt.date) -> pd.DataFrame:
    """Per-subscriber frequency/recency/age/monetary over [start, end)."""
    return con.execute(f"""
        SELECT sub_id,
               COUNT(*) - 1 AS x,
               datediff('day', MIN(date), MAX(date)) / {WEEK} AS t_x,
               datediff('day', MIN(date), DATE '{end}') / {WEEK} AS T,
               COUNT(*) AS n_tx,
               AVG(margin_bdt) AS avg_margin
        FROM fct_recharge WHERE date >= DATE '{start}' AND date < DATE '{end}'
        GROUP BY 1 ORDER BY 1""").df()


# ------------------------------------------------------------------ BG/NBD
@dataclass
class BGNBD:
    r: float
    alpha: float
    a: float
    b: float

    @staticmethod
    def loglik(params, x, t_x, T):
        r, alpha, a, b = params
        A1 = gammaln(r + x) - gammaln(r) + r * np.log(alpha)
        A2 = gammaln(a + b) + gammaln(b + x) - gammaln(b) - gammaln(a + b + x)
        A3 = -(r + x) * np.log(alpha + T)
        with np.errstate(divide="ignore", invalid="ignore"):
            A4 = np.where(x > 0, np.log(a) - np.log(b + x - 1) - (r + x) * np.log(alpha + t_x), -np.inf)
        return A1 + A2 + np.logaddexp(A3, A4)

    @classmethod
    def fit(cls, x, t_x, T) -> "BGNBD":
        x, t_x, T = map(np.asarray, (x, t_x, T))

        def nll(logp):
            return -cls.loglik(np.exp(logp), x, t_x, T).sum() / len(x)

        res = minimize(nll, x0=np.log([1.0, 1.0, 1.0, 1.0]), method="L-BFGS-B",
                       bounds=[(-8, 8)] * 4)
        if not res.success:
            raise RuntimeError(f"BG/NBD fit failed: {res.message}")
        return cls(*np.exp(res.x))

    def p_alive(self, x, t_x, T):
        r, alpha, a, b = self.r, self.alpha, self.a, self.b
        x, t_x, T = map(np.asarray, (x, t_x, T))
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(x > 0, (a / (b + x - 1)) * ((alpha + T) / (alpha + t_x)) ** (r + x), 0.0)
        return 1.0 / (1.0 + ratio)

    def expected_purchases(self, t, x, t_x, T):
        """E[Y(t) | x, t_x, T]: expected transactions in the next t weeks."""
        r, alpha, a, b = self.r, self.alpha, self.a, self.b
        x, t_x, T = map(np.asarray, (x, t_x, T))
        z = t / (alpha + T + t)
        hyp = hyp2f1(r + x, b + x, a + b + x - 1, z)
        num = (a + b + x - 1) / (a - 1) * (1 - ((alpha + T) / (alpha + T + t)) ** (r + x) * hyp)
        return num * self.p_alive(x, t_x, T)

    def simulate(self, n: int, T: float, rng: np.random.Generator) -> pd.DataFrame:
        """Draw synthetic customers from the model (used to test parameter recovery)."""
        lam = rng.gamma(self.r, 1 / self.alpha, n)
        p = rng.beta(self.a, self.b, n)
        x = np.zeros(n, dtype=int)
        t_x = np.zeros(n)
        for i in range(n):
            t = 0.0
            while True:
                t += rng.exponential(1 / lam[i])
                if t > T:
                    break
                x[i] += 1
                t_x[i] = t
                if rng.random() < p[i]:
                    break
        return pd.DataFrame({"x": x, "t_x": t_x, "T": T})


# ------------------------------------------------------------------ Gamma-Gamma
@dataclass
class GammaGamma:
    p: float
    q: float
    gamma: float

    @staticmethod
    def loglik(params, n, m):
        p, q, g = params
        return (gammaln(p * n + q) - gammaln(p * n) - gammaln(q) + q * np.log(g)
                + (p * n - 1) * np.log(m) + p * n * np.log(n) - (p * n + q) * np.log(g + m * n))

    @classmethod
    def fit(cls, n, m) -> "GammaGamma":
        n, m = np.asarray(n, float), np.asarray(m, float)

        def nll(logp):
            return -cls.loglik(np.exp(logp), n, m).sum() / len(n)

        res = minimize(nll, x0=np.log([1.0, 2.0, float(np.mean(m))]), method="L-BFGS-B",
                       bounds=[(-8, 8), (np.log(1.01), 12), (-8, 12)])
        if not res.success:
            raise RuntimeError(f"Gamma-Gamma fit failed: {res.message}")
        return cls(*np.exp(res.x))

    def expected_value(self, n, m):
        n, m = np.asarray(n, float), np.asarray(m, float)
        return (self.gamma + m * n) * self.p / (self.p * n + self.q - 1)

    @property
    def population_mean(self) -> float:
        return self.p * self.gamma / (self.q - 1)


# ------------------------------------------------------------------ fit + predict
@dataclass
class CLVModel:
    bgnbd: BGNBD
    gg: GammaGamma
    freq_monetary_corr: float


def fit_clv(df: pd.DataFrame) -> CLVModel:
    bg = BGNBD.fit(df.x, df.t_x, df["T"])
    rep = df[df.n_tx >= 2]
    gg = GammaGamma.fit(rep.n_tx, rep.avg_margin)
    corr = float(np.corrcoef(rep.n_tx, rep.avg_margin)[0, 1])
    return CLVModel(bg, gg, corr)


def predict_clv(model: CLVModel, df: pd.DataFrame, horizon_weeks: float) -> pd.DataFrame:
    out = df[["sub_id"]].copy()
    out["p_alive"] = model.bgnbd.p_alive(df.x, df.t_x, df["T"])
    out["exp_tx"] = model.bgnbd.expected_purchases(horizon_weeks, df.x, df.t_x, df["T"])
    out["exp_margin_per_tx"] = np.where(df.n_tx >= 2, model.gg.expected_value(df.n_tx, df.avg_margin),
                                        model.gg.population_mean)
    out["clv_pred"] = out.exp_tx * out.exp_margin_per_tx
    return out


def run_rate_baseline(con, end: dt.date, months: int, horizon_months: float) -> pd.DataFrame:
    """Average monthly margin over the last `months` months x horizon."""
    start = (pd.Timestamp(end) - pd.DateOffset(months=months)).date()
    return con.execute(f"""
        SELECT sub_id, SUM(margin_bdt) / {months} * {horizon_months} AS clv_baseline
        FROM fct_recharge WHERE date >= DATE '{start}' AND date < DATE '{end}' GROUP BY 1""").df()
