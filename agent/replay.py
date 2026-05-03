"""Replay capability.

Given an existing AgentRun (loaded from audit/agent_runs/), re-invoke the
agent against the same warehouse with the same inputs and compare. Replay
is *not* expected to produce byte-identical reasoning -- the LLM samples
tokens. We assert what should be stable:

  - same set of verdict defect_types
  - same severities
  - confidence within a tolerance
  - similar set of tool calls (Jaccard >= threshold)

Reasoning prose is allowed to vary freely.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .core import _RUN_DIR, run_agent
from .schemas import AgentRun, Verdict


@dataclass
class ReplayDiff:
    original_run_id: str
    replay_run_id: str
    same_defect_types: bool
    same_severities: bool
    confidence_max_delta: float
    tool_jaccard: float
    notes: list[str]
    matches_original: bool


def _load_run_dict(run_id: str, dir_path: Path | None = None) -> dict[str, Any]:
    dir_path = dir_path or _RUN_DIR
    p = dir_path / f"{run_id}.json"
    if not p.exists():
        raise FileNotFoundError(f"agent run not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def replay_agent(
    run_id: str,
    *,
    confidence_tolerance: float = 0.20,
    tool_jaccard_threshold: float = 0.50,
    dir_path: Path | None = None,
) -> tuple[AgentRun, ReplayDiff]:
    """Re-run the agent for the inputs of `run_id` and diff against the original.

    Returns the new AgentRun plus a ReplayDiff. The new run is persisted to
    `audit/agent_runs/` like any other run.
    """
    original = _load_run_dict(run_id, dir_path)

    fund_id = original["fund_id"]
    as_of_date = date.fromisoformat(original["as_of_date"])
    share_class = original.get("share_class")
    model = original.get("model_version")

    new_run = run_agent(
        fund_id=fund_id,
        as_of_date=as_of_date,
        share_class=share_class,
        model=model,
        run_id=None,  # let it generate a fresh id
    )

    diff = compare_runs(
        original=original, replay=new_run,
        confidence_tolerance=confidence_tolerance,
        tool_jaccard_threshold=tool_jaccard_threshold,
    )
    return new_run, diff


def compare_runs(
    original: dict[str, Any],
    replay: AgentRun,
    *,
    confidence_tolerance: float = 0.20,
    tool_jaccard_threshold: float = 0.50,
) -> ReplayDiff:
    """Compare an original run dict to a fresh AgentRun. Used by both
    replay_agent and tests that load saved runs."""
    notes: list[str] = []

    orig_verdicts = original.get("verdicts", []) or []
    repl_verdicts = replay.verdicts or []

    orig_types = {v.get("defect_type") for v in orig_verdicts
                  if v.get("defect_type") and v.get("defect_type") != "no_defect"}
    repl_types = {v.defect_type for v in repl_verdicts
                  if v.defect_type and v.defect_type != "no_defect"}
    same_defect_types = orig_types == repl_types
    if not same_defect_types:
        notes.append(
            f"defect_types differ: original={sorted(orig_types)} "
            f"replay={sorted(repl_types)}"
        )

    # Severity comparison: per defect_type, severity must match if both runs
    # produced a verdict for that type. Missing verdicts already counted above.
    same_severities = True
    orig_by_type = {v["defect_type"]: v for v in orig_verdicts
                    if v.get("defect_type") != "no_defect"}
    repl_by_type = {v.defect_type: v for v in repl_verdicts
                    if v.defect_type != "no_defect"}
    common = orig_types & repl_types
    for t in common:
        if orig_by_type[t].get("severity") != repl_by_type[t].severity:
            same_severities = False
            notes.append(
                f"severity differs for {t}: "
                f"original={orig_by_type[t].get('severity')} "
                f"replay={repl_by_type[t].severity}"
            )

    # Confidence delta.
    confidence_max_delta = 0.0
    for t in common:
        d = abs(float(orig_by_type[t].get("confidence", 0.0))
                - float(repl_by_type[t].confidence))
        confidence_max_delta = max(confidence_max_delta, d)
    if confidence_max_delta > confidence_tolerance:
        notes.append(
            f"confidence delta {confidence_max_delta:.3f} exceeds tolerance "
            f"{confidence_tolerance:.2f}"
        )

    # Tool-call Jaccard on tool name multisets compressed to sets.
    orig_tool_names = {tc.get("tool_name") for tc in (original.get("tool_call_log") or [])}
    repl_tool_names = {tc.tool_name for tc in replay.tool_call_log}
    union = orig_tool_names | repl_tool_names
    inter = orig_tool_names & repl_tool_names
    tool_jaccard = (len(inter) / len(union)) if union else 1.0
    if tool_jaccard < tool_jaccard_threshold:
        notes.append(
            f"tool overlap (Jaccard {tool_jaccard:.2f}) below threshold "
            f"{tool_jaccard_threshold:.2f}"
        )

    matches_original = (
        same_defect_types and same_severities
        and confidence_max_delta <= confidence_tolerance
        and tool_jaccard >= tool_jaccard_threshold
    )

    return ReplayDiff(
        original_run_id=original.get("run_id", ""),
        replay_run_id=replay.run_id,
        same_defect_types=same_defect_types,
        same_severities=same_severities,
        confidence_max_delta=confidence_max_delta,
        tool_jaccard=tool_jaccard,
        notes=notes,
        matches_original=matches_original,
    )
