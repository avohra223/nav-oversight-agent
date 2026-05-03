"""Load AgentRun JSON files and fund metadata for the UI.

The UI is a viewer over `audit/agent_runs/`. Files prefixed `fixture_` are
synthetic; once real runs are recorded, they appear in the same directory
and are rendered identically.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
AGENT_RUNS_DIR = ROOT / "audit" / "agent_runs"
TOOL_CALLS_LOG = ROOT / "audit" / "tool_calls.jsonl"


# ---------------------------------------------------------------------------
# Cached loaders
# ---------------------------------------------------------------------------
@st.cache_data(ttl=10, show_spinner=False)
def load_all_runs() -> list[dict[str, Any]]:
    """Return every AgentRun JSON in audit/agent_runs/, parsed.

    Cached for 10s so navigation between pages is fast; cache busts on
    file system change implicitly because the cache key includes the
    set of files (we sort by name as a stable cache key).
    """
    if not AGENT_RUNS_DIR.exists():
        return []
    runs: list[dict[str, Any]] = []
    for p in sorted(AGENT_RUNS_DIR.glob("*.json")):
        if p.name.startswith("_"):
            continue
        try:
            runs.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return runs


@st.cache_data(ttl=10, show_spinner=False)
def load_run(run_id: str) -> dict[str, Any] | None:
    p = AGENT_RUNS_DIR / f"{run_id}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


@st.cache_data(ttl=60, show_spinner=False)
def load_funds() -> pd.DataFrame:
    """Fund metadata from the warehouse via Phase 2 tool layer."""
    import sys
    sys.path.insert(0, str(ROOT))
    from tools.reference import get_funds
    rows = [
        {
            "fund_id": f.fund_id,
            "name": f.name,
            "base_ccy": f.base_ccy,
            "strategy": f.strategy,
            "tolerance_bps": f.tolerance_bps,
            "benchmark": f.benchmark,
        }
        for f in get_funds()
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------
def runs_for_date(runs: list[dict], target: date) -> list[dict]:
    return [r for r in runs if _as_date(r.get("as_of_date")) == target]


def runs_for_fund(runs: list[dict], fund_id: str) -> list[dict]:
    return [r for r in runs if r.get("fund_id") == fund_id]


def latest_run_per_fund(runs: list[dict]) -> dict[str, dict]:
    """Most recent run per fund (by started_at), keyed by fund_id."""
    by_fund: dict[str, dict] = {}
    for r in runs:
        fid = r.get("fund_id")
        if not fid:
            continue
        prev = by_fund.get(fid)
        if prev is None or _as_dt(r.get("started_at")) > _as_dt(prev.get("started_at")):
            by_fund[fid] = r
    return by_fund


def primary_severity(run: dict) -> str:
    """Highest severity across the run's verdicts.

    HIGH/CRITICAL > MEDIUM > LOW > NONE, treating no_defect as NONE.
    """
    rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "NONE": 0}
    best = "NONE"
    for v in run.get("verdicts") or []:
        if v.get("defect_type") == "no_defect":
            continue
        sev = v.get("severity", "NONE")
        if rank.get(sev, 0) > rank.get(best, 0):
            best = sev
    return best


def primary_action(run: dict) -> str:
    rank = {
        "BLOCK_NAV": 4, "URGENT_REVIEW": 3, "REVIEW_QUEUE": 2,
        "LOG_ONLY": 1, "AUTO_SIGN_OFF": 0,
    }
    best = "AUTO_SIGN_OFF"
    for a in run.get("policy_actions") or []:
        act = a.get("action", "AUTO_SIGN_OFF")
        if rank.get(act, 0) > rank.get(best, 0):
            best = act
    return best


def defect_count(run: dict) -> int:
    return sum(
        1 for v in (run.get("verdicts") or [])
        if v.get("defect_type") not in (None, "no_defect")
    )


def aggregate_metrics(runs: list[dict]) -> dict[str, Any]:
    n_runs = len(runs)
    blocked = sum(1 for r in runs if primary_action(r) == "BLOCK_NAV")
    defects_total = sum(defect_count(r) for r in runs)
    confs: list[float] = []
    for r in runs:
        for v in r.get("verdicts") or []:
            if v.get("defect_type") not in (None, "no_defect"):
                confs.append(float(v.get("confidence") or 0.0))
    avg_conf = sum(confs) / len(confs) if confs else None
    return {
        "n_runs": n_runs,
        "defects_total": defects_total,
        "blocked": blocked,
        "avg_confidence": avg_conf,
    }


def runs_to_dashboard_table(
    runs: list[dict], funds_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build the dashboard table: one row per fund's latest run."""
    by_fund = latest_run_per_fund(runs)
    rows: list[dict] = []
    for _, f in funds_df.iterrows():
        fid = f["fund_id"]
        r = by_fund.get(fid)
        if r is None:
            rows.append({
                "fund_id": fid,
                "name": f["name"],
                "as_of_date": None,
                "status": "not_run",
                "severity": "—",
                "action": "—",
                "defects": 0,
                "confidence": None,
                "iterations": None,
                "tokens": None,
                "latency_s": None,
                "run_id": None,
                "model": None,
                "started_at": None,
            })
            continue
        rows.append({
            "fund_id": fid,
            "name": f["name"],
            "as_of_date": r.get("as_of_date"),
            "status": "complete" if r.get("converged") else "halted",
            "severity": primary_severity(r),
            "action": primary_action(r),
            "defects": defect_count(r),
            "confidence": _highest_confidence(r),
            "iterations": r.get("iterations"),
            "tokens": ((r.get("token_usage") or {}).get("input_tokens", 0)
                       + (r.get("token_usage") or {}).get("output_tokens", 0)),
            "latency_s": (r.get("total_latency_ms") or 0) / 1000.0,
            "run_id": r.get("run_id"),
            "model": r.get("model_version"),
            "started_at": r.get("started_at"),
        })
    return pd.DataFrame(rows)


def runs_to_explorer_table(runs: list[dict]) -> pd.DataFrame:
    rows: list[dict] = []
    for r in runs:
        rows.append({
            "run_id": r.get("run_id"),
            "fund_id": r.get("fund_id"),
            "as_of_date": r.get("as_of_date"),
            "share_class": r.get("share_class"),
            "severity": primary_severity(r),
            "defect_type": _primary_defect_type(r),
            "action": primary_action(r),
            "confidence": _highest_confidence(r),
            "iterations": r.get("iterations"),
            "tokens_total": _tokens_total(r),
            "latency_s": (r.get("total_latency_ms") or 0) / 1000.0,
            "model": r.get("model_version"),
            "prompt_version": r.get("prompt_version"),
            "started_at": r.get("started_at"),
        })
    return pd.DataFrame(rows).sort_values("started_at", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _as_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (ValueError, TypeError):
        return None


def _as_dt(v: Any) -> datetime:
    if v is None:
        return datetime.min
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v))
    except (ValueError, TypeError):
        return datetime.min


def _highest_confidence(run: dict) -> float | None:
    confs = [
        float(v.get("confidence") or 0.0)
        for v in (run.get("verdicts") or [])
        if v.get("defect_type") not in (None, "no_defect")
    ]
    return max(confs) if confs else None


def _primary_defect_type(run: dict) -> str:
    for v in run.get("verdicts") or []:
        if v.get("defect_type") not in (None, "no_defect"):
            return v.get("defect_type")
    return "no_defect"


def _tokens_total(run: dict) -> int:
    tu = run.get("token_usage") or {}
    return sum(int(tu.get(k, 0) or 0) for k in (
        "input_tokens", "output_tokens",
        "cache_creation_input_tokens", "cache_read_input_tokens",
    ))
