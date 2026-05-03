"""Side-by-side comparison of two AgentRun records (used in the run explorer
to show original vs replay for a given investigation)."""
from __future__ import annotations

from typing import Any

import streamlit as st

from ..styling import severity_badge


def render_audit_diff(run_a: dict[str, Any], run_b: dict[str, Any]) -> None:
    """Render a two-column diff highlighting verdict / tool-call differences."""
    col_a, col_b = st.columns(2)
    with col_a:
        _render_one(run_a, label="Original")
    with col_b:
        _render_one(run_b, label="Replay")

    st.markdown("---")
    st.markdown("**Diff summary**")
    same_types = _verdict_types(run_a) == _verdict_types(run_b)
    same_sevs = _severities_match(run_a, run_b)
    tool_overlap = _tool_jaccard(run_a, run_b)

    cols = st.columns(3)
    cols[0].metric("Same defect types", "yes" if same_types else "no")
    cols[1].metric("Severities match", "yes" if same_sevs else "no")
    cols[2].metric("Tool overlap (Jaccard)", f"{tool_overlap:.2f}")


def _render_one(run: dict[str, Any], label: str) -> None:
    st.markdown(f"**{label}**")
    st.caption(f"run_id: `{run.get('run_id', '—')}`")
    for v in run.get("verdicts") or []:
        if v.get("defect_type") == "no_defect":
            continue
        st.markdown(
            f"{severity_badge(v.get('severity', 'NONE'))} "
            f"`{v.get('defect_type', '?')}` "
            f"(conf {float(v.get('confidence') or 0):.2f}, "
            f"bps {v.get('bps_impact')})",
            unsafe_allow_html=True,
        )


def _verdict_types(run: dict[str, Any]) -> set[str]:
    return {
        v.get("defect_type") for v in (run.get("verdicts") or [])
        if v.get("defect_type") and v.get("defect_type") != "no_defect"
    }


def _severities_match(a: dict, b: dict) -> bool:
    by_a = {v.get("defect_type"): v.get("severity")
            for v in (a.get("verdicts") or [])
            if v.get("defect_type") != "no_defect"}
    by_b = {v.get("defect_type"): v.get("severity")
            for v in (b.get("verdicts") or [])
            if v.get("defect_type") != "no_defect"}
    common = set(by_a) & set(by_b)
    return all(by_a[t] == by_b[t] for t in common)


def _tool_jaccard(a: dict, b: dict) -> float:
    tools_a = {tc.get("tool_name") for tc in (a.get("tool_call_log") or [])}
    tools_b = {tc.get("tool_name") for tc in (b.get("tool_call_log") or [])}
    union = tools_a | tools_b
    if not union:
        return 1.0
    return len(tools_a & tools_b) / len(union)
