"""Run the agent on a clean fund-day with no engineered defect; assert no
HIGH/CRITICAL severity verdicts. Some LOW-severity noise is acceptable
(the agent may flag minor anomalies; LOW is what LOG_ONLY is for).

We pick STERL on 2026-02-19 -- inside the window, no defect scheduled
on this day, no nearby defect on STERL.
"""
from __future__ import annotations

from datetime import date

from agent import run_agent
from nav_oversight.config import DEFECT_SCHEDULE


def _is_clean_day(fund_id: str, as_of: date, share_class: str | None) -> bool:
    for spec in DEFECT_SCHEDULE:
        if spec.fund_id != fund_id:
            continue
        # Defects can manifest on adjacent days; require ±2 buffer.
        if abs((spec.as_of - as_of).days) <= 2:
            return False
    return True


def test_agent_no_high_severity_on_clean_fund_day(api_key_required):
    fund_id = "STERL"
    as_of = date(2026, 2, 19)
    share_class = "I"
    assert _is_clean_day(fund_id, as_of, share_class), (
        "test target is not actually clean per DEFECT_SCHEDULE"
    )

    run = run_agent(
        fund_id=fund_id, as_of_date=as_of, share_class=share_class,
    )
    assert run.converged, run.halted_reason

    high_severity = [
        v for v in run.verdicts
        if v.severity in ("HIGH", "CRITICAL")
        and v.defect_type != "no_defect"
    ]
    if high_severity:
        # Surface what the agent thought was wrong so we can diagnose.
        msg = ["agent flagged HIGH-severity defects on a clean fund-day:"]
        for v in high_severity:
            msg.append(
                f"  - {v.defect_type} sev={v.severity} conf={v.confidence:.2f}"
            )
            msg.append(f"    reason: {v.reasoning[:300]}")
        raise AssertionError("\n".join(msg))
