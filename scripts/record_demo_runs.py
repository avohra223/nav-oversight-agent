"""Record real agent runs against the warehouse for demo replacement.

Use ONCE you have Anthropic API credit. By default this records the three
"hero" defects (3, 5, 9) which exercise the broadest reasoning patterns
(missed CA, perf-fee HWM logic, treaty-rate compliance). The output JSON
files end up in audit/agent_runs/ alongside the fixtures and replace any
matching fixture so the UI starts showing the real reasoning.

Usage:
    export ANTHROPIC_API_KEY=...
    python scripts/record_demo_runs.py                 # default trio
    python scripts/record_demo_runs.py --all           # all 10 defects
    python scripts/record_demo_runs.py --defect 3 9    # subset
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from agent import run_agent  # noqa: E402
from agent.core import save_agent_run  # noqa: E402
from nav_oversight.config import DEFECT_SCHEDULE  # noqa: E402


HERO_DEFECTS = (3, 5, 9)


def _select(defect_ids: tuple[int, ...]) -> list:
    return [d for d in DEFECT_SCHEDULE if d.defect_id in defect_ids]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--all", action="store_true",
                   help="Record all 10 defects.")
    p.add_argument("--defect", type=int, nargs="+",
                   help="Specific defect IDs to record.")
    p.add_argument("--model", default="claude-opus-4-7")
    args = p.parse_args()

    if args.all:
        targets = list(DEFECT_SCHEDULE)
    elif args.defect:
        targets = _select(tuple(args.defect))
    else:
        targets = _select(HERO_DEFECTS)

    print(f"Recording {len(targets)} run(s) against {args.model}.")
    print(
        "Estimated cost: "
        f"{len(targets)*1.5:.1f} - {len(targets)*2.5:.1f} USD on Opus, "
        f"{len(targets)*0.4:.1f} - {len(targets)*0.8:.1f} USD on Sonnet."
    )
    print()

    runs: list = []
    for spec in targets:
        print(f"  recording defect #{spec.defect_id} {spec.code}  "
              f"{spec.fund_id} {spec.as_of} cls={spec.share_class or '-'}")
        run = run_agent(
            fund_id=spec.fund_id,
            as_of_date=spec.as_of,
            share_class=spec.share_class,
            model=args.model,
        )
        save_agent_run(run)
        runs.append(run)
        print(f"    -> audit/agent_runs/{run.run_id}.json  "
              f"({run.iterations} iters, "
              f"{run.token_usage.input_tokens + run.token_usage.output_tokens:,d} tokens, "
              f"{len(run.verdicts)} verdicts)")
    print()
    print(f"Done. {len(runs)} run(s) recorded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
