"""CLI: run the agent against one (fund, date, [share class]).

Usage:
    python scripts/run_agent.py --fund AURORA --date 2026-03-12
    python scripts/run_agent.py --fund ATLAS --date 2026-03-05 --share-class A
    python scripts/run_agent.py --fund COBAL --date 2026-04-15 --share-class I \\
        --max-iterations 30
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from agent.core import (  # noqa: E402
    DEFAULT_MAX_ITERATIONS, DEFAULT_MAX_TOKENS_PER_RUN, DEFAULT_MODEL,
    run_agent,
)


def _print_run(run) -> None:
    print()
    print("=" * 78)
    print(f"AGENT RUN  {run.run_id}")
    print("=" * 78)
    print(f"  fund:           {run.fund_id}")
    print(f"  as_of:          {run.as_of_date}")
    print(f"  share_class:    {run.share_class or '-'}")
    print(f"  model:          {run.model_version}")
    print(f"  prompt_version: {run.prompt_version}")
    print(f"  iterations:     {run.iterations}")
    print(f"  tool calls:     {len(run.tool_call_log)}")
    print(f"  tokens (in):    {run.token_usage.input_tokens:>8,}")
    print(f"  tokens (out):   {run.token_usage.output_tokens:>8,}")
    print(f"  tokens (cache): {run.token_usage.cache_creation_input_tokens:>8,} created / "
          f"{run.token_usage.cache_read_input_tokens:>8,} read")
    print(f"  latency:        {run.total_latency_ms / 1000.0:.1f}s")
    print(f"  converged:      {run.converged}  ({run.halted_reason or 'end_turn'})")
    print()

    print(f"VERDICTS ({len(run.verdicts)})")
    print("-" * 78)
    for i, v in enumerate(run.verdicts, 1):
        bps = f"{v.bps_impact:+.1f}bps" if v.bps_impact is not None else "n/a"
        print(f"  [{i}] {v.defect_type:30s}  sev={v.severity:8s}  "
              f"conf={v.confidence:.2f}  impact={bps}")
        print(f"      action: {v.recommended_action}")
        # First sentence of reasoning, capped.
        first = v.reasoning.split(". ")[0].strip()
        if len(first) > 200:
            first = first[:200] + "..."
        print(f"      reason: {first}")
        if v.evidence:
            for j, e in enumerate(v.evidence[:3], 1):
                print(f"        evidence[{j}]: {e.description[:140]}")
            if len(v.evidence) > 3:
                print(f"        (+{len(v.evidence) - 3} more)")
        print()

    print(f"POLICY ACTIONS ({len(run.policy_actions)})")
    print("-" * 78)
    for i, a in enumerate(run.policy_actions, 1):
        esc = f" -> {a.escalate_to}" if a.escalate_to else ""
        print(f"  [{i}] {a.verdict_defect_type:30s}  {a.action:14s}{esc}  "
              f"(rule: {a.rule_matched})")
    print()


def main() -> int:
    p = argparse.ArgumentParser(description="Run the NAV oversight agent.")
    p.add_argument("--fund", required=True, help="Fund ID, e.g. AURORA")
    p.add_argument("--date", required=True, help="As-of date, YYYY-MM-DD")
    p.add_argument("--share-class", default=None,
                   help="Share class code (optional)")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"Anthropic model (default {DEFAULT_MODEL})")
    p.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS,
                   help=f"Max tool-use iterations (default {DEFAULT_MAX_ITERATIONS})")
    p.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS_PER_RUN,
                   help=f"Max total tokens (default {DEFAULT_MAX_TOKENS_PER_RUN})")
    args = p.parse_args()

    as_of = date.fromisoformat(args.date)
    run = run_agent(
        fund_id=args.fund,
        as_of_date=as_of,
        share_class=args.share_class,
        model=args.model,
        max_iterations=args.max_iterations,
        max_tokens_per_run=args.max_tokens,
    )
    _print_run(run)
    print(f"Audit record: audit/agent_runs/{run.run_id}.json")
    return 0 if run.converged else 1


if __name__ == "__main__":
    sys.exit(main())
