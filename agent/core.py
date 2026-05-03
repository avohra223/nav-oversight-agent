"""Agent loop: tool-use cycle against the warehouse, structured verdicts.

Public entry point: `run_agent(fund_id, as_of_date, share_class=None, ...)`.

The loop:
  1. Compose system prompt (cached) + initial user message.
  2. Call messages.create. If response has tool_use blocks, dispatch each
     to a Phase 2 tool, append tool_result blocks, loop.
  3. Stop when stop_reason == 'end_turn', max_iterations hit, or token
     budget exceeded.
  4. Parse the final response for a <verdicts>...</verdicts> JSON block.
  5. Apply the policy layer to each verdict.
  6. Persist an immutable AgentRun record to audit/agent_runs/{run_id}.json.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .api_wrapper import call_messages
from .dispatcher import (
    build_anthropic_tool_definitions, dispatch,
)
from .policies import apply_policy
from .schemas import (
    AgentRun, EvidenceItem, PolicyAction, ToolCall, TokenUsage, Verdict,
    DEFECT_TYPES, to_json_dict,
)
from .versioning import (
    defect_checklist_text, prompt_version, system_prompt_text,
)


DEFAULT_MODEL = "claude-opus-4-7"
DEFAULT_MAX_ITERATIONS = 50
DEFAULT_MAX_TOKENS_PER_RUN = 200_000
DEFAULT_MAX_OUTPUT_TOKENS_PER_TURN = 8192


_RUN_DIR = Path(__file__).resolve().parents[1] / "audit" / "agent_runs"
_VERDICTS_RE = re.compile(
    r"<verdicts>\s*(\[.*?\])\s*</verdicts>", re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def run_agent(
    fund_id: str,
    as_of_date: date | str,
    share_class: str | None = None,
    *,
    run_id: str | None = None,
    model: str = DEFAULT_MODEL,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    max_tokens_per_run: int = DEFAULT_MAX_TOKENS_PER_RUN,
    max_output_tokens_per_turn: int = DEFAULT_MAX_OUTPUT_TOKENS_PER_TURN,
    persist: bool = True,
    extra_user_directives: str | None = None,
) -> AgentRun:
    """Run the agent against one (fund, date, optional share_class).

    Returns an AgentRun. If persist=True, writes audit/agent_runs/{run_id}.json.
    """
    if isinstance(as_of_date, str):
        as_of_date = date.fromisoformat(as_of_date)

    run_id = run_id or _make_run_id(fund_id, as_of_date)
    started_at = datetime.utcnow()
    t0 = time.perf_counter()

    # System content: two cached blocks (system prompt + checklist).
    system = [
        {
            "type": "text",
            "text": system_prompt_text(),
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": defect_checklist_text(),
            "cache_control": {"type": "ephemeral"},
        },
    ]
    tools = build_anthropic_tool_definitions(cache_last=True)

    # Initial user message.
    user_text = _build_user_message(fund_id, as_of_date, share_class,
                                    extra_user_directives)
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_text},
    ]

    tool_call_log: list[ToolCall] = []
    token_usage = TokenUsage()
    iteration = 0
    converged = True
    halted_reason: str | None = None
    final_response = None
    final_text = ""

    while iteration < max_iterations:
        if token_usage.input_tokens + token_usage.output_tokens > max_tokens_per_run:
            converged = False
            halted_reason = "token_budget"
            break

        try:
            response, usage = call_messages(
                model=model,
                system=system,
                tools=tools,
                messages=messages,
                max_tokens=max_output_tokens_per_turn,
            )
        except Exception as e:
            converged = False
            halted_reason = f"api_error: {type(e).__name__}: {e}"
            break

        token_usage.add(usage)
        final_response = response
        iteration += 1

        # Append assistant turn (preserve content blocks for tool_use_id chaining).
        assistant_blocks = _content_blocks_to_dict(response.content)
        messages.append({"role": "assistant", "content": assistant_blocks})

        if response.stop_reason == "end_turn":
            final_text = _extract_text(assistant_blocks)
            break
        if response.stop_reason == "max_tokens":
            converged = False
            halted_reason = "max_output_tokens_hit_in_turn"
            final_text = _extract_text(assistant_blocks)
            break
        if response.stop_reason != "tool_use":
            # 'stop_sequence' or unknown -> finalize whatever we have.
            final_text = _extract_text(assistant_blocks)
            break

        # Dispatch tool uses.
        tool_results: list[dict[str, Any]] = []
        for block in assistant_blocks:
            if block.get("type") != "tool_use":
                continue
            tool_use_id = block.get("id")
            tool_name = block.get("name")
            raw_args = block.get("input", {}) or {}
            payload, call_record = dispatch(
                tool_name=tool_name,
                raw_args=raw_args,
                iteration=iteration,
                tool_use_id=tool_use_id,
            )
            tool_call_log.append(call_record)
            is_error = isinstance(payload, dict) and payload.get("is_error") is True
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": json.dumps(payload, default=str),
                "is_error": bool(is_error),
            })

        messages.append({"role": "user", "content": tool_results})

    if iteration >= max_iterations and (
        final_response is None or final_response.stop_reason != "end_turn"
    ):
        converged = False
        halted_reason = "max_iterations"

    # Parse verdicts.
    verdicts = _parse_verdicts(final_text)
    if not converged and not verdicts:
        verdicts = [Verdict(
            defect_type="agent_did_not_converge",
            severity="MEDIUM",
            confidence=0.0,
            evidence=[EvidenceItem(
                description=f"Agent halted: {halted_reason}",
            )],
            recommended_action="URGENT_REVIEW",
            reasoning=(
                f"The agent did not produce a structured verdict block. "
                f"Halted reason: {halted_reason}. Iterations completed: "
                f"{iteration}. Token usage: {token_usage.total}."
            ),
            bps_impact=None,
        )]

    # Apply policy.
    policy_actions = [apply_policy(v, fund_id) for v in verdicts]

    finished_at = datetime.utcnow()
    total_latency_ms = (time.perf_counter() - t0) * 1000.0

    run = AgentRun(
        run_id=run_id,
        fund_id=fund_id,
        as_of_date=as_of_date,
        share_class=share_class,
        model_version=model,
        prompt_version=prompt_version(),
        verdicts=verdicts,
        policy_actions=policy_actions,
        tool_call_log=tool_call_log,
        message_history=messages,
        token_usage=token_usage,
        total_latency_ms=total_latency_ms,
        iterations=iteration,
        converged=converged,
        halted_reason=halted_reason,
        started_at=started_at,
        finished_at=finished_at,
    )

    if persist:
        save_agent_run(run)

    return run


def save_agent_run(run: AgentRun, dir_path: Path | None = None) -> Path:
    """Persist an AgentRun to audit/agent_runs/{run_id}.json."""
    dir_path = dir_path or _RUN_DIR
    dir_path.mkdir(parents=True, exist_ok=True)
    out = dir_path / f"{run.run_id}.json"
    out.write_text(
        json.dumps(to_json_dict(run), indent=2, default=str),
        encoding="utf-8",
    )
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_run_id(fund_id: str, as_of_date: date) -> str:
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"{ts}_{fund_id}_{as_of_date.isoformat()}_{suffix}"


def _build_user_message(
    fund_id: str, as_of_date: date, share_class: str | None,
    extra_user_directives: str | None,
) -> str:
    sc = f", share class {share_class}" if share_class else ""
    base = (
        f"Evaluate the pre-close NAV pack for fund {fund_id}{sc} on "
        f"{as_of_date.isoformat()}. Work through the defect checklist. Use "
        "tools to gather evidence. Reconcile the day's NAV move in basis "
        "points against the drivers you identify. Produce one or more "
        "structured verdicts inside <verdicts>...</verdicts> at the end of "
        "your final response."
    )
    if extra_user_directives:
        return base + "\n\n" + extra_user_directives
    return base


def _content_blocks_to_dict(content: Any) -> list[dict[str, Any]]:
    """Convert SDK content blocks to plain dicts so they round-trip through
    JSON and can be replayed."""
    out: list[dict[str, Any]] = []
    for block in content:
        t = getattr(block, "type", None) or block.get("type") if isinstance(block, dict) else None
        if t == "text":
            text = getattr(block, "text", None) if not isinstance(block, dict) else block.get("text")
            out.append({"type": "text", "text": text})
        elif t == "tool_use":
            out.append({
                "type": "tool_use",
                "id": getattr(block, "id", None) if not isinstance(block, dict) else block.get("id"),
                "name": getattr(block, "name", None) if not isinstance(block, dict) else block.get("name"),
                "input": getattr(block, "input", None) if not isinstance(block, dict) else block.get("input"),
            })
        elif t == "thinking":
            txt = getattr(block, "thinking", None) if not isinstance(block, dict) else block.get("thinking")
            out.append({"type": "thinking", "thinking": txt})
        else:
            # Unknown block type; coerce.
            if isinstance(block, dict):
                out.append(block)
            else:
                out.append({"type": str(t)})
    return out


def _extract_text(blocks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for b in blocks:
        if b.get("type") == "text" and b.get("text"):
            parts.append(b["text"])
    return "\n\n".join(parts)


def _parse_verdicts(text: str) -> list[Verdict]:
    """Extract the <verdicts>[...]</verdicts> JSON block and validate."""
    if not text:
        return []
    m = _VERDICTS_RE.search(text)
    if not m:
        return []
    raw = m.group(1)
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []

    verdicts: list[Verdict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            v = _coerce_verdict(item)
            verdicts.append(v)
        except (ValueError, TypeError, KeyError):
            # Skip malformed verdicts; the run is still useful.
            continue
    return verdicts


def _coerce_verdict(d: dict[str, Any]) -> Verdict:
    defect_type = str(d.get("defect_type", "no_defect"))
    if defect_type not in DEFECT_TYPES:
        defect_type = "no_defect"
    severity = str(d.get("severity", "NONE")).upper()
    if severity not in ("LOW", "MEDIUM", "HIGH", "CRITICAL", "NONE"):
        severity = "NONE"
    confidence = float(d.get("confidence", 0.0))
    confidence = max(0.0, min(1.0, confidence))
    recommended_action = str(d.get("recommended_action", "LOG_ONLY")).upper()
    if recommended_action not in (
        "AUTO_SIGN_OFF", "LOG_ONLY", "REVIEW_QUEUE",
        "URGENT_REVIEW", "BLOCK_NAV",
    ):
        recommended_action = "LOG_ONLY"
    bps_impact = d.get("bps_impact")
    if bps_impact is not None:
        try:
            bps_impact = float(bps_impact)
        except (TypeError, ValueError):
            bps_impact = None

    raw_evidence = d.get("evidence") or []
    evidence: list[EvidenceItem] = []
    if isinstance(raw_evidence, list):
        for e in raw_evidence:
            if not isinstance(e, dict):
                continue
            evidence.append(EvidenceItem(
                description=str(e.get("description", "")),
                source_table=e.get("source_table"),
                source_key=e.get("source_key") or {},
                source_fields=list(e.get("source_fields") or []),
                observed_value=e.get("observed_value"),
                expected_value=e.get("expected_value"),
            ))

    return Verdict(
        defect_type=defect_type,
        severity=severity,  # type: ignore[arg-type]
        confidence=confidence,
        evidence=evidence,
        recommended_action=recommended_action,  # type: ignore[arg-type]
        reasoning=str(d.get("reasoning", "")),
        bps_impact=bps_impact,
    )
