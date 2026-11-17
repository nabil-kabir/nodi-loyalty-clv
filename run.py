"""One command to rebuild everything:  python run.py   (or  python run.py --sample  for a fast 20k build)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from nodi.config import load_config  # noqa: E402

STEPS = ["simulate", "warehouse", "models", "segments", "offers", "messages", "report"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", action="store_true", help="20k-subscriber build into data_sample/")
    ap.add_argument("--only", choices=STEPS, help="run a single step")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--live", action="store_true", help="messages: call the Anthropic API (needs ANTHROPIC_API_KEY)")
    g.add_argument("--mock", action="store_true", help="messages: use only the on-disk cache (default without a key)")
    ap.add_argument("--seed-messages", action="store_true",
                    help="messages: (re)write the labelled seed copy into the cache first (never overwrites API output)")
    args = ap.parse_args()
    cfg = load_config(sample=args.sample)
    steps = [args.only] if args.only else STEPS

    if "simulate" in steps:
        from nodi.simulate.run import simulate
        simulate(cfg)
    if "warehouse" in steps:
        from nodi.warehouse.build import build_warehouse
        build_warehouse(cfg)
    if "models" in steps:
        from nodi.models.run import run_models
        run_models(cfg)
    if "segments" in steps:
        from nodi.segments.build import build_segments
        build_segments(cfg)
    if "offers" in steps:
        from nodi.offers.run import run_offers
        run_offers(cfg)
    if "messages" in steps:
        from nodi.messaging.run import run_messages
        if args.seed_messages:
            from nodi.messaging.seed import write_seed
            print(f"[messages] seeded {write_seed(cfg)} cell/language entries", flush=True)
        mode = "live" if args.live else "mock" if args.mock else None
        print("[messages]", run_messages(cfg, mode=mode), flush=True)
    if "report" in steps:
        from nodi.segments.build import phase4_report
        from nodi.validate.phase5 import phase5_validation
        from nodi.validate.phase1 import phase1_report
        from nodi.validate.phase3 import phase3_validation
        from nodi.validate.phase4 import phase4_validation
        from nodi.warehouse.report import phase2_report
        phase1_report(cfg)
        print("[report] phase 2 (metrics, data quality, fault injection)", flush=True)
        print(phase2_report(cfg), flush=True)
        print("[report] phase 3 validation against planted truth", flush=True)
        phase3_validation(cfg)
        print("[report] phase 4 segments + validation", flush=True)
        phase4_report(cfg)
        phase4_validation(cfg)
        print("[report] phase 5 validation against planted truth", flush=True)
        phase5_validation(cfg)


if __name__ == "__main__":
    main()
