"""End-to-end suite: run the agent against all 10 seeded defect fund-days
and produce a scoreboard. Asserts the agent detects at least 9 of 10.

Each test row is parameterized from src/nav_oversight/config.DEFECT_SCHEDULE
so the test is the single source of truth for "what should the agent find."
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from agent import run_agent
from agent.schemas import Verdict
from nav_oversight.config import DEFECT_SCHEDULE


_RESULTS_PATH = Path(__file__).resolve().parents[2] / "audit" / "agent_runs" / "_full_suite_scoreboard.json"


@dataclass
class _Row:
    defect_id: int
    code: str
    fund_id: str
    share_class: str | None
    detected: bool
    severity: str | None
    confidence: float | None
    bps_impact: float | None
    converged: bool
    iterations: int
    total_tokens: int
    notes: str = ""


@pytest.fixture(scope="module")
def scoreboard(api_key_required) -> list[_Row]:
    """Run the agent against every seeded defect fund-day, build scoreboard."""
    rows: list[_Row] = []
    for spec in DEFECT_SCHEDULE:
        run = run_agent(
            fund_id=spec.fund_id,
            as_of_date=spec.as_of,
            share_class=spec.share_class,
        )
        match: Verdict | None = None
        for v in run.verdicts:
            if v.defect_type == spec.code:
                match = v
                break
        rows.append(_Row(
            defect_id=spec.defect_id,
            code=spec.code,
            fund_id=spec.fund_id,
            share_class=spec.share_class,
            detected=match is not None,
            severity=match.severity if match else None,
            confidence=match.confidence if match else None,
            bps_impact=match.bps_impact if match else None,
            converged=run.converged,
            iterations=run.iterations,
            total_tokens=run.token_usage.total,
            notes="" if match else (
                "verdict types produced: "
                + ", ".join(v.defect_type for v in run.verdicts)
            ),
        ))

    # Persist for the user to inspect.
    _RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _RESULTS_PATH.write_text(
        json.dumps([row.__dict__ for row in rows], indent=2),
        encoding="utf-8",
    )
    return rows


def test_full_suite_print_scoreboard(scoreboard):
    """Always prints; never fails. Useful when the threshold test below fails."""
    print()
    print(f"{'#':>2}  {'code':28s}  {'fund':6s}  {'cls':3s}  detected  sev   conf  bps    iter  tokens")
    print("-" * 100)
    for r in scoreboard:
        sev = (r.severity or "-")[:6]
        conf = f"{r.confidence:.2f}" if r.confidence is not None else "-   "
        bps = f"{r.bps_impact:+7.1f}" if r.bps_impact is not None else "  -    "
        det = "  YES   " if r.detected else "  NO    "
        cls = r.share_class or "-"
        print(
            f"{r.defect_id:>2}  {r.code:28s}  {r.fund_id:6s}  {cls:3s}  "
            f"{det}   {sev:6s} {conf:5s}  {bps}  {r.iterations:>4}  {r.total_tokens:>6,d}"
        )
        if r.notes:
            print(f"      notes: {r.notes}")
    detected = sum(r.detected for r in scoreboard)
    print("-" * 100)
    print(f"  detected: {detected} / {len(scoreboard)}")


def test_full_suite_at_least_9_of_10_detected(scoreboard):
    detected = [r for r in scoreboard if r.detected]
    missed = [r for r in scoreboard if not r.detected]
    assert len(detected) >= 9, (
        f"agent detected only {len(detected)}/10 defects. "
        f"missed: {[(r.defect_id, r.code) for r in missed]}\n"
        f"see audit/agent_runs/_full_suite_scoreboard.json"
    )


def test_full_suite_all_runs_converged(scoreboard):
    incomplete = [r for r in scoreboard if not r.converged]
    assert not incomplete, (
        "some runs did not converge: "
        + ", ".join(f"defect {r.defect_id} ({r.code})" for r in incomplete)
    )


def test_full_suite_high_severity_only_when_confident(scoreboard):
    """When the agent assigns HIGH/CRITICAL severity, confidence should be
    >= 0.5; very low confidence with high severity is a calibration issue."""
    bad = [
        r for r in scoreboard
        if r.detected and r.severity in ("HIGH", "CRITICAL")
        and (r.confidence or 0.0) < 0.5
    ]
    assert not bad, (
        "high-severity verdicts with low confidence: "
        + ", ".join(f"{r.code}:conf={r.confidence}" for r in bad)
    )
