"""Churn propensity: LightGBM + isotonic calibration, with two baselines a CVM team already has.

Backtest (honest, strictly out-of-time):
    train        2025-04-01, 2025-05-01, 2025-06-01   labels observable by 2025-12-28
    calibrate    2025-07-01                           labels observable by 2025-12-28
    test         2026-01-01                           model has never seen anything from 2026
Production: retrain on 2025-04..2025-10, calibrate on 2026-01, score 2026-07-01.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .features import CATEGORICAL, FEATURES, NUMERIC

D = dt.date
BACKTEST = dict(train=[D(2025, 4, 1), D(2025, 5, 1), D(2025, 6, 1)], calib=[D(2025, 7, 1)], test=[D(2026, 1, 1)])
PRODUCTION = dict(train=[D(2025, m, 1) for m in range(4, 11)], calib=[D(2026, 1, 1)], score=D(2026, 7, 1))

LGB_PARAMS = dict(
    objective="binary", learning_rate=0.05, n_estimators=400, num_leaves=31, min_child_samples=200,
    subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
    random_state=7, deterministic=True, force_row_wise=True, n_jobs=4, verbose=-1,
)


@dataclass
class ChurnModel:
    booster: lgb.LGBMClassifier
    iso: IsotonicRegression

    def raw(self, X: pd.DataFrame) -> np.ndarray:
        return self.booster.predict_proba(X[FEATURES])[:, 1]

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.iso.predict(self.raw(X))

    def contributions(self, X: pd.DataFrame) -> pd.DataFrame:
        """Per-feature SHAP values (log-odds), LightGBM's native TreeSHAP."""
        c = self.booster.predict(X[FEATURES], pred_contrib=True)
        return pd.DataFrame(c[:, :-1], columns=FEATURES, index=X.index)


def fit_churn(train: pd.DataFrame, calib: pd.DataFrame) -> ChurnModel:
    clf = lgb.LGBMClassifier(**LGB_PARAMS)
    clf.fit(train[FEATURES], train["churn_90d"], categorical_feature=CATEGORICAL)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1)
    iso.fit(clf.predict_proba(calib[FEATURES])[:, 1], calib["churn_90d"])
    return ChurnModel(clf, iso)


def fit_logistic(train: pd.DataFrame):
    pre = ColumnTransformer([
        ("num", make_pipeline(StandardScaler()), NUMERIC),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
    ])
    pipe = make_pipeline(pre, LogisticRegression(max_iter=1000))
    X = train[FEATURES].copy()
    X[NUMERIC] = X[NUMERIC].fillna(0)
    pipe.fit(X, train["churn_90d"])
    return pipe


def logistic_predict(pipe, df: pd.DataFrame) -> np.ndarray:
    X = df[FEATURES].copy()
    X[NUMERIC] = X[NUMERIC].fillna(0)
    return pipe.predict_proba(X)[:, 1]


def bau_rule(df: pd.DataFrame) -> np.ndarray:
    """The operator's existing win-back trigger: recharges in last 30d fell below half of prior 30d."""
    return ((df.rech_prev30 >= 2) & (df.rech_30 < 0.5 * df.rech_prev30)).to_numpy()


def decile_table(y: np.ndarray, score: np.ndarray) -> pd.DataFrame:
    """Decile 1 = highest risk. Lift = churn rate in decile / overall churn rate."""
    order = np.argsort(-score, kind="stable")
    dec = np.empty(len(y), dtype=int)
    dec[order] = np.arange(len(y)) * 10 // len(y) + 1
    df = pd.DataFrame({"decile": dec, "y": y, "p": score})
    t = df.groupby("decile").agg(subscribers=("y", "size"), churners=("y", "sum"),
                                 churn_rate=("y", "mean"), avg_predicted=("p", "mean")).reset_index()
    t["lift"] = t.churn_rate / y.mean()
    t["cum_capture"] = t.churners.cumsum() / y.sum()
    return t


def gains_curve(y: np.ndarray, score: np.ndarray, points: int = 101) -> pd.DataFrame:
    order = np.argsort(-score, kind="stable")
    cum = np.concatenate([[0], np.cumsum(y[order])]) / y.sum()
    x = np.linspace(0, 1, points)
    return pd.DataFrame({"share_targeted": x, "share_churners_reached": cum[(x * len(y)).astype(int)]})


def evaluate(y: np.ndarray, p: np.ndarray) -> dict:
    t = decile_table(y, p)
    return {
        "auc": roc_auc_score(y, p), "pr_auc": average_precision_score(y, p),
        "brier": brier_score_loss(y, p), "base_rate": y.mean(),
        "top_decile_lift": t.lift.iloc[0], "capture_top10": t.cum_capture.iloc[0],
        "capture_top20": t.cum_capture.iloc[1],
    }
