"""End-to-end agent test: defect 9 (wrong WHT on AURORA's Samsung dividend)."""
from __future__ import annotations

from datetime import date

import pytest

from agent import run_agent


def test_agent_detects_wrong_wht_on_aurora_2026_03_12(api_key_required):
    run = run_agent(fund_id="AURORA", as_of_date=date(2026, 3, 12))

    assert run.converged, (
        f"agent did not converge: halted_reason={run.halted_reason}, "
        f"iterations={run.iterations}, tokens={run.token_usage.total}\n"
        f"verdicts={run.verdicts}"
    )
    assert run.verdicts

    matches = [v for v in run.verdicts if v.defect_type == "wrong_wht"]
    assert matches, (
        f"agent did not flag wrong_wht. Verdicts produced:\n"
        + "\n".join(
            f"  {v.defect_type} sev={v.severity} conf={v.confidence:.2f}"
            for v in run.verdicts
        )
    )
    v = matches[0]

    assert v.severity in ("LOW", "MEDIUM", "HIGH", "CRITICAL"), v.severity
    assert v.confidence >= 0.70, (
        f"confidence too low: {v.confidence:.2f}: reasoning={v.reasoning}"
    )
    assert v.recommended_action in (
        "BLOCK_NAV", "URGENT_REVIEW", "REVIEW_QUEUE", "LOG_ONLY",
    ), v.recommended_action

    # Evidence should mention Samsung / Korea / treaty rate.
    evidence_text = " ".join(e.description for e in v.evidence).lower()
    reasoning = v.reasoning.lower()
    combined = evidence_text + " " + reasoning
    assert (
        "samsung" in combined
        or "samsu" in combined
        or "korea" in combined
        or "kr " in combined
        or " kr" in combined
        or "treaty" in combined
    ), f"evidence/reasoning missing expected references: {combined[:300]!r}"
