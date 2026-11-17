"""Validation summary for the app. Lives in nodi.validate because it is assembled from comparisons
with the planted truth (reports written by phase3/phase5 validation); the app only displays it."""
from __future__ import annotations

import json
from pathlib import Path


def _read(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def validation_summary(cfg: dict) -> dict:
    rep = Path(cfg["paths"]["reports"])
    v3, v5, m3 = (_read(rep / "phase3" / "truth_validation.json"), _read(rep / "phase5" / "truth_validation.json"),
                  _read(rep / "phase3" / "metrics.json"))
    return {
        "note": "Comparisons with the planted ground truth (the hidden counterfactual simulation), computed by "
                "nodi.validate. The app only displays these summaries.",
        "churn_backtest": m3.get("churn_backtest"), "clv_holdout": m3.get("clv_holdout"),
        "churn_vs_truth": v3.get("churn"), "drivers": v3.get("drivers"), "clv_vs_truth": v3.get("clv"),
        "plans_vs_truth": v5.get("at_budget"),
    }
