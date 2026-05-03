"""End-to-end agent test: defect 3 (missed corporate action on HELIO/AAPL)."""
from __future__ import annotations

from datetime import date

import pytest

from agent import run_agent


def test_agent_detects_missed_ca_on_helio_2026_04_02(api_key_required):
    run = run_agent(fund_id="HELIO", as_of_date=date(2026, 4, 2))

    # The run must converge and produce a verdicts block.
    assert run.converged, (
        f"agent did not converge: halted_reason={run.halted_reason}, "
        f"iterations={run.iterations}, "
        f"tokens={run.token_usage.total}\n"
        f"verdicts={run.verdicts}"
    )
    assert run.verdicts, (
        f"agent produced no verdicts. tool_calls="
        f"{[tc.tool_name for tc in run.tool_call_log]}"
    )

    # Find a verdict for missed_corp_action.
    matches = [v for v in run.verdicts if v.defect_type == "missed_corp_action"]
    assert matches, (
        f"agent did not flag missed_corp_action. Verdicts produced:\n"
        + "\n".join(
            f"  {v.defect_type} sev={v.severity} conf={v.confidence:.2f}"
            for v in run.verdicts
        )
    )
    v = matches[0]

    # Required guarantees.
    assert v.severity in ("MEDIUM", "HIGH", "CRITICAL"), (
        f"unexpected severity {v.severity!r}: reasoning={v.reasoning}"
    )
    assert v.confidence >= 0.70, (
        f"confidence too low: {v.confidence:.2f}: reasoning={v.reasoning}"
    )
    assert v.recommended_action in (
        "BLOCK_NAV", "URGENT_REVIEW", "REVIEW_QUEUE",
    ), f"unexpected action {v.recommended_action!r}"

    # Evidence must reference AAPL or the missed receipt.
    evidence_text = " ".join(e.description for e in v.evidence).lower()
    assert (
        "aapl" in evidence_text
        or "eq_us_aapl" in evidence_text
        or "apple" in evidence_text
    ), f"evidence does not mention AAPL: {evidence_text!r}"
