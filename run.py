"""One command to rebuild everything:  python run.py   (or  python run.py --sample  for a fast 20k build)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from nodi.config import load_config  # noqa: E402

STEPS = ["simulate", "warehouse", "report"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", action="store_true", help="20k-subscriber build into data_sample/")
    ap.add_argument("--only", choices=STEPS, help="run a single step")
    args = ap.parse_args()
    cfg = load_config(sample=args.sample)
    steps = [args.only] if args.only else STEPS

    if "simulate" in steps:
        from nodi.simulate.run import simulate
        simulate(cfg)
    if "warehouse" in steps:
        from nodi.warehouse.build import build_warehouse
        build_warehouse(cfg)
    if "report" in steps:
        from nodi.validate.phase1 import phase1_report
        from nodi.warehouse.report import phase2_report
        phase1_report(cfg)
        print("[report] phase 2 (metrics, data quality, fault injection)", flush=True)
        print(phase2_report(cfg), flush=True)


if __name__ == "__main__":
    main()
