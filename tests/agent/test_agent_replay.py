"""Replay test: run the agent on a complex defect, replay it, and verify
the verdicts and tool calls are stable across runs.

We pick defect 5 (stale HWM perf fee on COBAL Class I 2026-04-15) because
it requires multi-step reasoning across multiple tools (NAV history,
share-class fee terms, fee accruals, perf-fee math).

Replay tolerances:
  - same set of non-trivial defect_types
  - same severity per matching defect_type
  - confidence within 0.20
  - tool-name Jaccard >= 0.50
"""
from __future__ import annotations

from datetime import date

import pytest

from agent import run_agent, replay_agent, compare_runs
from agent.core import save_agent_run


def test_agent_replay_stable_for_complex_defect(api_key_required, capsys):
    # Original run.
    original = run_agent(
        fund_id="COBAL",
        as_of_date=date(2026, 4, 15),
        share_class="I",
    )
    assert original.converged
    save_agent_run(original)

    # Replay.
    replay_run, diff = replay_agent(
        original.run_id,
        confidence_tolerance=0.20,
        tool_jaccard_threshold=0.50,
    )

    # Print the diff regardless so we see it in test output.
    print()
    print(f"original run: {diff.original_run_id}")
    print(f"replay   run: {diff.replay_run_id}")
    print(f"  same_defect_types:    {diff.same_defect_types}")
    print(f"  same_severities:      {diff.same_severities}")
    print(f"  confidence_max_delta: {diff.confidence_max_delta:.3f}")
    print(f"  tool_jaccard:         {diff.tool_jaccard:.2f}")
    print(f"  matches_original:     {diff.matches_original}")
    if diff.notes:
        for n in diff.notes:
            print(f"  note: {n}")

    assert diff.matches_original, (
        "replay did not match original within tolerances. "
        f"notes={diff.notes}"
    )
