"""Tabular view of tool calls with input / output / latency."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st


def render_tool_call_table(tool_call_log: list[dict[str, Any]]) -> None:
    if not tool_call_log:
        st.markdown('<div class="dim">No tool calls.</div>', unsafe_allow_html=True)
        return

    rows = []
    for tc in tool_call_log:
        args = tc.get("arguments") or {}
        summary = tc.get("result_summary") or {}
        rows.append({
            "iter": tc.get("iteration", 0),
            "tool": tc.get("tool_name", "?"),
            "args": _compact_args(args),
            "result": _summary(summary),
            "latency_ms": round(float(tc.get("latency_ms") or 0.0), 1),
            "error": tc.get("error") or "",
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "iter": st.column_config.NumberColumn("Iter", width="small"),
            "tool": st.column_config.TextColumn("Tool", width="medium"),
            "args": st.column_config.TextColumn("Arguments", width="large"),
            "result": st.column_config.TextColumn("Result Summary", width="medium"),
            "latency_ms": st.column_config.NumberColumn(
                "Latency (ms)", format="%.1f", width="small",
            ),
            "error": st.column_config.TextColumn("Error", width="medium"),
        },
    )


def _compact_args(args: dict[str, Any]) -> str:
    parts: list[str] = []
    for k, v in args.items():
        if v is None:
            continue
        s = str(v) if not isinstance(v, (dict, list)) else json.dumps(v, default=str)
        if len(s) > 28:
            s = s[:25] + "…"
        parts.append(f"{k}={s}")
    return "  ".join(parts)


def _summary(s: dict[str, Any]) -> str:
    t = s.get("type")
    if t == "DataFrame":
        return f"df rows={s.get('rows', 0)} cols={s.get('cols', 0)}"
    if t == "list":
        return f"list rows={s.get('rows', 0)} of {s.get('element_type') or '?'}"
    if t == "None":
        return "no rows"
    if "value" in s:
        v = s["value"]
        if isinstance(v, str) and len(v) > 30:
            v = v[:27] + "…"
        return f"{t} = {v}"
    return t or "—"
