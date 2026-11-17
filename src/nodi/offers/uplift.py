"""Uplift (heterogeneous treatment effect) models, trained ONLY on the randomised Jan-2026 pilot.

Two effects per offer:
  margin   : extra contribution margin in the 90-day window (spend lift + early retention)
  retention: reduction in 90-day churn probability
Incremental 12-month value of an offer before cost:
  value(x) = tau_margin(x) + tau_retention(x) x value_if_retained_12m(x) x 0.75
The first quarter is measured directly. After it, only the subscribers we kept carry value
forward (9 of 12 months), so nothing is counted twice.

Why this design (DECISIONS 5.2-5.4): with 8k subscribers per arm and small effects, raw uplift
scores are mostly noise, and an optimiser hunts that noise ("winner's curse"). So:
1. Candidate personalisation scores, all cross-fitted on the pilot:
     t_learner  : LightGBM model per arm, treated minus control
     dr_ridge   : doubly-robust pseudo-outcome regressed on 12 interpretable features (low variance)
     redemption : predicted probability of redeeming the offer (does the effect travel with redemption?)
2. For each offer x outcome, a Best Linear Predictor test (Chernozhukov et al. 2018) on held-out
   predictions measures how much of each score's heterogeneity is real (beta2). We keep the
   candidate with the strongest significant beta2 (t > 1.64); if none passes, everyone gets the ATE.
3. The ATE is used only if significantly positive (one-sided 5%), then shrunk by ate^2 / (ate^2 + se^2).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import KFold
from sklearn.preprocessing import StandardScaler

from nodi.models.features import CATEGORICAL, FEATURES, snapshot
from nodi.simulate.catalog import OFFER_IDS

PILOT_DATE = dt.date(2026, 1, 1)
CARRY_FORWARD = 0.75
P_ARM = 0.2
OUTCOMES = {"margin": "margin_90d", "retention": "retained"}

REG = dict(n_estimators=150, learning_rate=0.03, num_leaves=8, min_child_samples=300,
           subsample=0.8, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0,
           random_state=7, deterministic=True, force_row_wise=True, n_jobs=4, verbose=-1)
SMALL = ["avg_recharge_90", "rech_90", "rech_trend", "days_since_last_event", "tenure_months",
         "is_smartphone", "data_mb_30", "active_days_30", "n_packs_90", "mfs_share_90", "dormant_spells_365"]


def pilot_frame(con) -> pd.DataFrame:
    f = snapshot(con, PILOT_DATE, with_label=False)
    po = con.execute("SELECT sub_id, arm, churned::INT AS churned, margin_90d, redeemed::INT AS redeemed "
                     "FROM mart_pilot_outcome ORDER BY sub_id").df()
    # explicit sort: DuckDB row order is not deterministic, and cross-fitting is positional
    d = po.merge(f, on="sub_id", how="inner").sort_values("sub_id").reset_index(drop=True)
    d["retained"] = 1 - d.churned
    return d


def lin_X(d: pd.DataFrame) -> pd.DataFrame:
    X = d[SMALL].fillna(0).astype(float).copy()
    X["rural"] = (d.area_type.astype(str) == "rural").astype(float)
    X["log_avg_recharge"] = np.log1p(X.pop("avg_recharge_90"))
    X["log_data_mb"] = np.log1p(X.pop("data_mb_30"))
    return X


def _reg(X, y):
    return lgb.LGBMRegressor(**REG).fit(X, y, categorical_feature=CATEGORICAL)


def _clf(X, y):
    return lgb.LGBMClassifier(**REG).fit(X, y, categorical_feature=CATEGORICAL)


# ------------------------------------------------------------------ candidate learners
class TLearnerScore:
    def fit(self, d, T, y):
        self.m1, self.m0 = _reg(d[FEATURES][T == 1], y[T == 1]), _reg(d[FEATURES][T == 0], y[T == 0])
        return self

    def predict(self, X):
        return self.m1.predict(X[FEATURES]) - self.m0.predict(X[FEATURES])


class DRRidgeScore:
    """DR-learner: nuisance models cross-fitted inside fit(); final stage ridge on interpretable features."""
    def fit(self, d, T, y, folds=3, seed=11):
        psi = np.zeros(len(d))
        for tr, te in KFold(folds, shuffle=True, random_state=seed).split(d):
            a, Ta, ya = d.iloc[tr], T[tr], y[tr]
            m1, m0 = _reg(a[FEATURES][Ta == 1], ya[Ta == 1]), _reg(a[FEATURES][Ta == 0], ya[Ta == 0])
            b = d.iloc[te]
            mu1, mu0 = m1.predict(b[FEATURES]), m0.predict(b[FEATURES])
            p = T.mean()
            psi[te] = mu1 - mu0 + T[te] * (y[te] - mu1) / p - (1 - T[te]) * (y[te] - mu0) / (1 - p)
        self.sc = StandardScaler().fit(lin_X(d))
        self.r = RidgeCV(alphas=np.logspace(0, 4, 9)).fit(self.sc.transform(lin_X(d)), psi)
        return self

    def predict(self, X):
        return self.r.predict(self.sc.transform(lin_X(X)))


class RedemptionScore:
    def fit(self, d, T, y):
        self.m = _clf(d[FEATURES][T == 1], d.redeemed[T == 1])
        return self

    def predict(self, X):
        return self.m.predict_proba(X[FEATURES])[:, 1]


CANDIDATES = {"t_learner": TLearnerScore, "dr_ridge": DRRidgeScore, "redemption": RedemptionScore}


def _arm(df, offer):
    d = df[df.arm.isin([offer, "control"])].reset_index(drop=True)
    return d, (d.arm == offer).to_numpy().astype(float)


def cross_fit_scores(df: pd.DataFrame, folds: int = 5, seed: int = 7) -> dict:
    """Out-of-fold candidate scores: {(offer, outcome, candidate): array aligned to _arm(df, offer)}."""
    out = {}
    for o in OFFER_IDS:
        d, T = _arm(df, o)
        for outcome, col in OUTCOMES.items():
            y = d[col].to_numpy().astype(float)
            for name, cls in CANDIDATES.items():
                if name == "redemption" and outcome == "retention":
                    pass  # redemption score is outcome-agnostic but tested against both outcomes
                s = np.zeros(len(d))
                for tr, te in KFold(folds, shuffle=True, random_state=seed).split(d):
                    s[te] = cls().fit(d.iloc[tr], T[tr], y[tr]).predict(d.iloc[te])
                out[(o, outcome, name)] = s
    return out


def blp(y: np.ndarray, T: np.ndarray, s: np.ndarray) -> dict:
    p = T.mean()
    sbar = s.mean()
    Xm = np.column_stack([np.ones(len(y)), s, T - p, (T - p) * (s - sbar)])
    beta, *_ = np.linalg.lstsq(Xm, y, rcond=None)
    res = y - Xm @ beta
    inv = np.linalg.inv(Xm.T @ Xm)
    cov = inv @ ((Xm * res[:, None] ** 2).T @ Xm) @ inv * len(y) / (len(y) - 4)
    se = np.sqrt(np.diag(cov))
    return {"ate": beta[2], "ate_se": se[2], "beta2": beta[3], "beta2_se": se[3], "s_bar": sbar}


@dataclass
class UpliftModel:
    calibration: pd.DataFrame                       # one row per offer x outcome x candidate
    chosen: pd.DataFrame                            # one row per offer x outcome
    fitted: dict = field(default_factory=dict)      # (offer, outcome) -> fitted chosen learner or None

    def effect(self, offer: str, outcome: str, X: pd.DataFrame) -> np.ndarray:
        r = self.chosen[(self.chosen.offer_id == offer) & (self.chosen.outcome == outcome)].iloc[0]
        base = np.full(len(X), r.ate_shrunk)
        model = self.fitted.get((offer, outcome))
        if model is None or r.beta2_used == 0:
            return base
        return base + r.beta2_used * (model.predict(X) - r.s_bar)


def fit_uplift(df: pd.DataFrame, oof: dict | None = None) -> UpliftModel:
    oof = oof or cross_fit_scores(df)
    rows = []
    for o in OFFER_IDS:
        d, T = _arm(df, o)
        for outcome, col in OUTCOMES.items():
            y = d[col].to_numpy().astype(float)
            for name in CANDIDATES:
                b = blp(y, T, oof[(o, outcome, name)])
                rows.append({"offer_id": o, "outcome": outcome, "candidate": name, **b,
                             "beta2_t": b["beta2"] / b["beta2_se"]})
    cal = pd.DataFrame(rows)
    chosen = []
    for (o, outcome), g in cal.groupby(["offer_id", "outcome"], sort=False):
        ate, ate_se = g.ate.mean(), g.ate_se.mean()  # identical up to the control covariate
        # act only on effects the pilot can distinguish from zero (one-sided 5%), then shrink
        shrink = ate ** 2 / (ate ** 2 + ate_se ** 2) if ate / ate_se > 1.64 else 0.0
        ok = g[(g.beta2_t > 1.64) & (g.beta2 > 0)]
        if len(ok):
            best = ok.sort_values("beta2_t", ascending=False).iloc[0]
            # effect-scale scores (t_learner, dr_ridge) are capped at full loading 1.0; the
            # redemption score is a probability, so its beta2 is in Tk per unit of probability
            b2 = float(best.beta2) if best.candidate == "redemption" else float(min(best.beta2, 1.0))
            cand, sbar, t = best.candidate, best.s_bar, best.beta2_t
        else:
            cand, b2, sbar, t = "none (average effect)", 0.0, 0.0, np.nan
        chosen.append({"offer_id": o, "outcome": outcome, "ate": ate, "ate_se": ate_se, "shrink": shrink,
                       "ate_shrunk": ate * shrink, "candidate": cand, "beta2_used": b2, "beta2_t": t,
                       "s_bar": sbar})
    chosen = pd.DataFrame(chosen)
    model = UpliftModel(cal, chosen)
    for r in chosen.itertuples():
        if r.beta2_used > 0:
            d, T = _arm(df, r.offer_id)
            y = d[OUTCOMES[r.outcome]].to_numpy().astype(float)
            model.fitted[(r.offer_id, r.outcome)] = CANDIDATES[r.candidate]().fit(d, T, y)
    return model


@dataclass
class RedemptionModel:
    models: dict
    oof_auc: dict

    def predict(self, offer: str, X: pd.DataFrame) -> np.ndarray:
        return self.models[offer].predict_proba(X[FEATURES])[:, 1]


def fit_redemption(df: pd.DataFrame, seed: int = 7) -> RedemptionModel:
    models, auc = {}, {}
    for o in OFFER_IDS:
        t = df[df.arm == o].reset_index(drop=True)
        p = np.zeros(len(t))
        for tr, te in KFold(5, shuffle=True, random_state=seed).split(t):
            p[te] = _clf(t.iloc[tr][FEATURES], t.redeemed.iloc[tr]).predict_proba(t.iloc[te][FEATURES])[:, 1]
        auc[o] = roc_auc_score(t.redeemed, p)
        models[o] = _clf(t[FEATURES], t.redeemed)
    return RedemptionModel(models, auc)


# ------------------------------------------------------------------ observable evaluation
def policy_value_ipw(df: pd.DataFrame, assigned: np.ndarray, cost_per_redeemer: dict, contact: float) -> dict:
    """Value of an assignment on the randomised pilot (inverse propensity weighting, 5 equal arms).

    `assigned[i]` is the arm policy gives pilot subscriber i ('control' = nothing). Uses ACTUAL
    redemptions for cost. Returns incremental 90-day margin net of cost per pilot subscriber vs
    contacting nobody, with a standard error.
    """
    arm = df.arm.to_numpy()
    cost = np.where(arm == "control", 0.0,
                    contact + df.redeemed.to_numpy() * pd.Series(arm).map(cost_per_redeemer).fillna(0).to_numpy())
    y = df.margin_90d.to_numpy() - cost
    diff = ((arm == assigned) * y - (arm == "control") * df.margin_90d.to_numpy()) / P_ARM
    return {"net_inc_per_sub": float(diff.mean()), "se": float(diff.std(ddof=1) / np.sqrt(len(diff))),
            "share_treated": float((assigned != "control").mean())}


def qini_curve(y: np.ndarray, T: np.ndarray, score: np.ndarray, points: int = 51) -> pd.DataFrame:
    """Observed cumulative incremental outcome treating the top-x% by score (randomised data)."""
    o = np.argsort(-score, kind="stable")
    y, T = y[o], T[o].astype(bool)
    yt, yc = np.cumsum(np.where(T, y, 0)), np.cumsum(np.where(~T, y, 0))
    nt, nc = np.cumsum(T), np.cumsum(~T)
    with np.errstate(divide="ignore", invalid="ignore"):
        inc = yt - yc * np.where(nc > 0, nt / nc, 0)
    x = np.linspace(0, 1, points)
    idx = np.clip((x * len(y)).astype(int) - 1, 0, len(y) - 1)
    return pd.DataFrame({"share_targeted": x, "incremental": np.where(x == 0, 0, inc[idx])})
