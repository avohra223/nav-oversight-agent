"""Evidence chain: timeline view of every tool call in a run."""
from __future__ import annotations

import json
from typing import Any

import streamlit as st

from ..styling import mono


def render_evidence_chain(tool_call_log: list[dict[str, Any]]) -> None:
    """Render the agent's full tool-call timeline as a numbered list with
    expandable per-call detail."""
    if not tool_call_log:
        st.markdown(
            '<div class="dim">No tool calls recorded for this run.</div>',
            unsafe_allow_html=True,
        )
        return

    # Group by iteration so the user can see "what the agent did per turn".
    by_iter: dict[int, list[dict]] = {}
    for tc in tool_call_log:
        by_iter.setdefault(int(tc.get("iteration", 0)), []).append(tc)

    for it in sorted(by_iter):
        st.markdown(
            f'<div class="panel-meta" style="margin-top: 12px;">Iteration {it}</div>',
            unsafe_allow_html=True,
        )
        for j, tc in enumerate(by_iter[it]):
            _render_call_row(tc, j + 1)


def _render_call_row(tc: dict[str, Any], idx: int) -> None:
    name = tc.get("tool_name") or "?"
    args = tc.get("arguments") or {}
    summary = tc.get("result_summary") or {}
    latency = tc.get("latency_ms") or 0.0
    error = tc.get("error")

    arg_chips = " ".join(
        f'<span class="mono" style="background:#292524; padding:1px 6px; '
        f'border-radius:2px; margin-right:4px; color:#d6d3d1; '
        f'font-size:0.78rem;">{k}={_compact(v)}</span>'
        for k, v in args.items() if v is not None
    )

    summary_text = _summary_text(summary)

    border = "#7f1d1d" if error else "#292524"
    st.markdown(
        f"""
<div style="background: #1c1917; border: 1px solid {border}; border-left: 3px solid {border};
            border-radius: 3px; padding: 8px 12px; margin-bottom: 6px;
            display: flex; justify-content: space-between; gap: 16px;
            align-items: center;">
  <div style="flex: 1;">
    <div>
      <span class="mono" style="color:#f5f5f4; font-weight:600;">{name}</span>
      <span style="margin-left: 10px;">{arg_chips}</span>
    </div>
    <div style="color:#a8a29e; font-size: 0.78rem; margin-top: 4px;">
      {summary_text}
    </div>
  </div>
  <div style="text-align: right; white-space: nowrap;">
    <div class="mono numeric" style="color:#d6d3d1; font-size:0.82rem;">
      {latency:.1f} ms
    </div>
    {(f'<div style="color:#f87171; font-size:0.72rem; margin-top:2px;">{error}</div>') if error else ''}
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def _summary_text(summary: dict[str, Any]) -> str:
    t = summary.get("type", "?")
    if t == "DataFrame":
        return f"DataFrame  rows={summary.get('rows', 0):,}  cols={summary.get('cols', 0)}"
    if t == "list":
        return (
            f"list  rows={summary.get('rows', 0):,}  "
            f"of {summary.get('element_type') or '?'}"
        )
    if t == "None":
        return "no rows"
    if "value" in summary:
        return f"{t} = {_compact(summary['value'])}"
    return t


def _compact(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, str):
        return v if len(v) <= 24 else v[:21] + "…"
    if isinstance(v, dict):
        if len(v) <= 2:
            return "{" + ", ".join(f"{k}:{_compact(val)}" for k, val in v.items()) + "}"
        return "{" + str(len(v)) + " keys}"
    if isinstance(v, list):
        return f"[{len(v)} items]"
    return str(v)
