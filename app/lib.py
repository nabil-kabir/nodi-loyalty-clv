"""Shared helpers for the Nodi app: data loading (app_data/ only), formatting, banner, live allocation."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "app_data"
sys.path.insert(0, str(ROOT / "src"))  # only for the dependency-free SMS validator

TEAL, TEAL_LIGHT, AMBER, GREY, INK, RED = "#0f766e", "#99d5cf", "#b45309", "#9ca3af", "#1f2937", "#b91c1c"
OFFER_LABEL = {"bonus_data": "Bonus data", "recharge_cashback": "Recharge cashback",
               "tenure_reward": "Tenure reward", "bundle_discount": "Bundle discount", "reminder": "Pack reminder"}
OFFER_COLOR = {"bonus_data": TEAL, "recharge_cashback": AMBER, "tenure_reward": GREY,
               "bundle_discount": "#6366f1", "reminder": "#d1d5db"}
STANCE_LABEL = {"invest": "Invest", "test": "Test", "low_cost": "Low cost", "no_spend": "No spend", "protect": "Protect"}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Bengali:wght@400;600&display=swap');
html, body, [class*="css"] { font-family: "Source Sans Pro", "Noto Sans Bengali", sans-serif; }
.block-container { padding-top: 2.2rem; max-width: 1180px; }
.nodi-banner { background:#fff7ed; border:1px solid #fed7aa; color:#7c2d12; border-radius:8px;
  padding:.45rem .8rem; font-size:.86rem; margin-bottom:1rem; }
.nodi-callout { background:#f0fdfa; border-left:4px solid #0f766e; border-radius:6px; padding:.9rem 1.1rem;
  font-size:1.08rem; line-height:1.5; margin:.4rem 0 1.2rem 0; }
.nodi-muted { color:#6b7280; font-size:.86rem; }
.nodi-phone { border:1px solid #e5e7eb; border-radius:14px; padding:.8rem .95rem; background:#f9fafb;
  font-family: "Noto Sans Bengali", "Source Sans Pro", sans-serif; font-size:1.0rem; line-height:1.55;
  min-height: 7.5rem; }
.nodi-tag { display:inline-block; font-size:.74rem; padding:.05rem .45rem; border-radius:99px;
  background:#e5e7eb; color:#374151; margin-right:.3rem; }
.nodi-ok { background:#dcfce7; color:#166534; } .nodi-bad { background:#fee2e2; color:#991b1b; }
[data-testid="stMetricValue"] { font-size: 1.75rem; }
[data-testid="stMetricLabel"] p { white-space: normal; }
@media (prefers-color-scheme: dark) {
  .nodi-banner { background:#3b2412; border-color:#7c2d12; color:#fed7aa; }
  .nodi-callout { background:#0b2e2b; }
  .nodi-phone { background:#111827; border-color:#374151; }
}
</style>
"""


def page_setup(title: str):
    st.markdown(CSS, unsafe_allow_html=True)
    h = headline()
    st.markdown(
        f'<div class="nodi-banner"><b>Synthetic data.</b> Nodi Telecom is a fictional operator and every '
        f'number here comes from simulated subscribers. Figures are shown at operator scale '
        f'(a 1% sample × {h["operator_scale"]}).</div>', unsafe_allow_html=True)
    st.title(title)


# ------------------------------------------------------------------ loading (cached)
@st.cache_data
def headline() -> dict:
    return json.loads((DATA / "headline.json").read_text(encoding="utf-8"))


@st.cache_data
def validation() -> dict:
    return json.loads((DATA / "validation.json").read_text(encoding="utf-8"))


@st.cache_data
def table(name: str) -> pd.DataFrame:
    return pd.read_parquet(DATA / f"{name}.parquet")


@st.cache_data
def messages() -> pd.DataFrame:
    return pd.DataFrame(json.loads((DATA / "messages.json").read_text(encoding="utf-8"))["messages"])


@st.cache_data
def messaging_spec() -> dict:
    return yaml.safe_load((ROOT / "messaging.yml").read_text(encoding="utf-8"))


@st.cache_data
def segments_spec() -> dict:
    return yaml.safe_load((ROOT / "segments.yml").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ formatting (lakh / crore)
def bdt(x: float, digits: int = 2) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    sign = "−" if x < 0 else ""
    a = abs(x)
    if a >= 1e7:
        return f"{sign}৳{a / 1e7:,.{digits}f} crore"
    if a >= 1e5:
        return f"{sign}৳{a / 1e5:,.1f} lakh"
    return f"{sign}৳{a:,.0f}"


def people(n: float) -> str:
    if n >= 1e7:
        return f"{n / 1e7:,.2f} crore"
    if n >= 1e5:
        return f"{n / 1e5:,.1f} lakh"
    return f"{n:,.0f}"


def bdt_short(x: float) -> str:
    """Compact taka for metric tiles: ৳3.11 cr, ৳45.2 L, ৳9,500."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    sign = "−" if x < 0 else ""
    a = abs(x)
    if a >= 0.995e7:  # round before choosing the unit: ৳99.98 lakh reads as ৳1.00 cr
        c = a / 1e7
        return f"{sign}৳{c:,.0f} cr" if c >= 100 else f"{sign}৳{c:,.1f} cr" if c >= 10 else f"{sign}৳{c:,.2f} cr"
    if a >= 1e5:
        return f"{sign}৳{a / 1e5:,.1f} L"
    return f"{sign}৳{a:,.0f}"


def people_short(n: float) -> str:
    if n >= 1e7:
        return f"{n / 1e7:,.2f} cr"
    if n >= 1e5:
        return f"{n / 1e5:,.1f} L"
    return f"{n:,.0f}"


def pct(x: float, d: int = 1) -> str:
    return f"{x * 100:.{d}f}%"


# ------------------------------------------------------------------ live allocation
@st.cache_data
def _steps(view: str):
    s = table("plan_steps" if view == "network" else "plan_steps_face")
    return s, s.cum_cost.to_numpy(), s.cum_net.to_numpy()


def optimised(budget_operator: float, view: str = "network") -> dict:
    scale = headline()["operator_scale"]
    s, cc, cn = _steps(view)
    i = int(np.searchsorted(cc, budget_operator / scale, side="right"))
    taken = s.iloc[:i]
    final = taken.drop_duplicates("sub_id", keep="last")
    return {"spend": (cc[i - 1] if i else 0.0) * scale, "net": (cn[i - 1] if i else 0.0) * scale,
            "targeted": len(final) * scale, "allocation": final[["sub_id", "offer_id"]]}


@st.cache_data
def _baseline_arrays():
    b = table("baseline_subscribers")
    out = {}
    for name, col in (("highest_churn_risk", "risk_rank"), ("blanket", "random_rank")):
        o = b.sort_values(col)
        out[name] = (o.best_cost.cumsum().to_numpy(), o.best_net.cumsum().to_numpy())
    return out


def baseline(name: str, budget_operator: float) -> dict:
    scale = headline()["operator_scale"]
    cc, cn = _baseline_arrays()[name]
    i = int(np.searchsorted(cc, budget_operator / scale, side="right"))
    return {"spend": (cc[i - 1] if i else 0.0) * scale, "net": (cn[i - 1] if i else 0.0) * scale,
            "targeted": i * scale}


@st.cache_data
def frontier(view: str, points: int = 61) -> pd.DataFrame:
    """Expected net margin vs budget for the optimiser and both baselines (array lookups only)."""
    h = headline()
    scale = h["operator_scale"]
    grid = np.linspace(0, h["slider_max_bdt"], points)
    _, cc, cn = _steps(view)
    out = {"budget": grid}
    i = np.searchsorted(cc, grid / scale, side="right")
    out["Optimised"] = np.where(i > 0, cn[np.maximum(i - 1, 0)], 0.0) * scale
    for name, label in (("blanket", "Blanket cashback"), ("highest_churn_risk", "Cashback to highest churn risk")):
        bc, bn = _baseline_arrays()[name]
        j = np.searchsorted(bc, grid / scale, side="right")
        out[label] = np.where(j > 0, bn[np.maximum(j - 1, 0)], 0.0) * scale
    return pd.DataFrame(out)


def mde(sigma: float, n_t: float, n_h: float) -> float:
    if n_t <= 0 or n_h <= 0:
        return float("nan")
    return 2.80158 * sigma * math.sqrt(1 / n_t + 1 / n_h)  # z(0.975) + z(0.80), 5% two-sided, 80% power


def plotly_layout(fig, height=360, **kw):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=30, b=10), font=dict(size=13),
                      legend=dict(orientation="h", y=-0.18), plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)", **kw)
    fig.update_xaxes(gridcolor="rgba(148,163,184,.25)")
    fig.update_yaxes(gridcolor="rgba(148,163,184,.25)")
    return fig
