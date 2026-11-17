"""Load config.yaml and resolve paths. One place for every tunable number."""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _merge(base: dict, extra: dict) -> dict:
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config(path: Path | None = None, sample: bool = False,
                data_dir: Path | None = None, overrides: dict | None = None) -> dict:
    with open(path or ROOT / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg = copy.deepcopy(cfg)
    if sample:
        cfg["simulation"]["n_subscribers"] = cfg["simulation"]["sample_n_subscribers"]
    if overrides:
        _merge(cfg, overrides)
    base = Path(data_dir) if data_dir else ROOT / ("data_sample" if sample else "data")
    cfg["paths"] = {
        "data": base,
        "raw": base / "raw",
        # Ground truth: written by nodi.simulate, read ONLY by nodi.validate (enforced by a test).
        "truth": base / "ground_truth",
        "reports": ROOT / "reports" if not sample and data_dir is None else base / "reports",
    }
    return cfg
