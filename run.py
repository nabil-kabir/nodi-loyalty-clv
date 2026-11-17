"""One command to rebuild everything:  python run.py   (or  python run.py --sample  for a fast 20k build)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from nodi.config import load_config  # noqa: E402

STEPS = ["simulate", "report"]


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
    if "report" in steps:
        from nodi.validate.phase1 import phase1_report
        phase1_report(cfg)


if __name__ == "__main__":
    main()
