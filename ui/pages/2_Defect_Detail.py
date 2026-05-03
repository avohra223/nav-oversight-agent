"""Defect detail: full evidence chain and verdicts for one run."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from ui.styling import (  # noqa: E402
    apply_enterprise_theme, page_header, mono,
)
from ui.data_loaders import load_all_runs, load_run  # noqa: E402
from ui.components import (  # noqa: E402
    render_verdict_card, render_evidence_chain, render_tool_call_table,
)


st.set_page_config(page_title="Defect Detail", layout="wide")
apply_enterprise_theme()


# ---------------------------------------------------------------------------
# Run picker
# ---------------------------------------------------------------------------
runs = load_all_runs()
options: list[tuple[str, str]] = [
    (r.get("run_id"),
     f'{r.get("fund_id")}  {r.get("as_of_date","")[:10]}'
     f'{("  cls "+r.get("share_class")) if r.get("share_class") else ""}'
     f'  ({(r.get("verdicts")[0].get("defect_type") if r.get("verdicts") else "—")})')
    for r in sorted(runs, key=lambda x: x.get("started_at") or "", reverse=True)
]

selected = st.session_state.get("selected_run_id")
if not selected and options:
    selected = options[0][0]

picker_cols = st.columns([6, 2])
with picker_cols[0]:
    if options:
        labels = [f"{rid}  —  {desc}" for rid, desc in options]
        idx = next((i for i, (rid, _) in enumerate(options) if rid == selected), 0)
        chosen_label = st.selectbox(
            "Run", labels, index=idx, label_visibility="collapsed",
        )
        selected = options[labels.index(chosen_label)][0]
        st.session_state["selected_run_id"] = selected
    else:
        st.warning("No runs in audit/agent_runs/. Generate fixtures first.")
        st.stop()

with picker_cols[1]:
    if st.button("Back to dashboard", use_container_width=True, type="secondary"):
        st.switch_page("pages/1_Dashboard.py")

run = load_run(selected) if selected else None
if run is None:
    st.error(f"Run not found: {selected}")
    st.stop()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
page_header(
    f"{run.get('fund_id')}  —  {run.get('as_of_date','')[:10]}",
    f"Investigation by single-agent multi-defect oversight loop. "
    f"Verdicts: {len(run.get('verdicts') or [])}",
)

meta_cols = st.columns(6)
meta_cols[0].markdown(
    f'<div class="panel-meta">Run ID</div>'
    f'<div class="mono" style="color:#d6d3d1; font-size: 0.78rem; word-break:break-all;">'
    f'{run.get("run_id","—")}</div>',
    unsafe_allow_html=True,
)
meta_cols[1].markdown(
    f'<div class="panel-meta">Share class</div>'
    f'<div>{run.get("share_class") or "—"}</div>',
    unsafe_allow_html=True,
)
meta_cols[2].markdown(
    f'<div class="panel-meta">Model</div>'
    f'<div class="mono">{run.get("model_version","—")}</div>',
    unsafe_allow_html=True,
)
meta_cols[3].markdown(
    f'<div class="panel-meta">Prompt version</div>'
    f'<div class="mono">{run.get("prompt_version","—")}</div>',
    unsafe_allow_html=True,
)
tu = run.get("token_usage") or {}
total_tokens = sum(int(tu.get(k, 0) or 0) for k in (
    "input_tokens", "output_tokens",
    "cache_creation_input_tokens", "cache_read_input_tokens",
))
meta_cols[4].markdown(
    f'<div class="panel-meta">Tokens</div>'
    f'<div class="mono numeric">{total_tokens:,d}</div>',
    unsafe_allow_html=True,
)
meta_cols[5].markdown(
    f'<div class="panel-meta">Latency</div>'
    f'<div class="mono numeric">{(run.get("total_latency_ms") or 0)/1000:.1f} s</div>',
    unsafe_allow_html=True,
)

st.markdown("---")

# ---------------------------------------------------------------------------
# Tabs: Verdicts | Evidence Chain | Tool Calls | Raw
# ---------------------------------------------------------------------------
tab_verdicts, tab_evidence, tab_tools, tab_raw = st.tabs([
    "Verdicts", "Evidence chain", "Tool calls", "Raw audit",
])

with tab_verdicts:
    verdicts = run.get("verdicts") or []
    if not verdicts:
        st.markdown('<div class="dim">No verdicts in this run.</div>',
                    unsafe_allow_html=True)
    for i, v in enumerate(verdicts, 1):
        render_verdict_card(v, i)

    # Policy actions row
    actions = run.get("policy_actions") or []
    if actions:
        st.markdown(
            '<div class="panel" style="margin-top: 16px;">'
            '<div class="panel-title">Policy actions</div>',
            unsafe_allow_html=True,
        )
        for a in actions:
            esc = f' &middot; escalate to <span class="mono">{a.get("escalate_to")}</span>' if a.get("escalate_to") else ""
            ch = f' &middot; notify <span class="mono">{a.get("notification_channel")}</span>' if a.get("notification_channel") else ""
            st.markdown(
                f'<div style="padding: 6px 0; border-top: 1px solid #292524;'
                f' color:#d6d3d1; font-size: 0.9rem;">'
                f'<span class="mono">{a.get("verdict_defect_type")}</span> '
                f'&rarr; <strong>{a.get("action")}</strong>'
                f'{esc}{ch}'
                f' <span class="dim">(rule: {a.get("rule_matched")})</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

with tab_evidence:
    render_evidence_chain(run.get("tool_call_log") or [])

with tab_tools:
    render_tool_call_table(run.get("tool_call_log") or [])

with tab_raw:
    st.markdown('<div class="panel-meta">Full message history</div>',
                unsafe_allow_html=True)
    msg_history = run.get("message_history") or []
    with st.expander(f"Show {len(msg_history)} messages", expanded=False):
        for i, msg in enumerate(msg_history):
            role = msg.get("role", "?")
            color = "#0369a1" if role == "user" else "#15803d"
            st.markdown(
                f'<div style="margin-top: 10px; color: {color}; '
                f'font-size: 0.78rem; text-transform: uppercase; '
                f'letter-spacing: 0.06em;">{i:03d}  {role}</div>',
                unsafe_allow_html=True,
            )
            content = msg.get("content")
            if isinstance(content, str):
                st.code(content, language="markdown")
            elif isinstance(content, list):
                for block in content:
                    bt = block.get("type")
                    if bt == "text":
                        st.code(block.get("text", ""), language="markdown")
                    elif bt == "tool_use":
                        st.code(
                            f"tool_use: {block.get('name')}\n"
                            f"id: {block.get('id')}\n"
                            + json.dumps(block.get("input", {}), indent=2,
                                         default=str),
                            language="json",
                        )
                    elif bt == "tool_result":
                        s = block.get("content")
                        try:
                            s = json.dumps(json.loads(s), indent=2, default=str)
                        except (json.JSONDecodeError, TypeError):
                            pass
                        st.code(
                            f"tool_result for {block.get('tool_use_id')}\n{s}",
                            language="json",
                        )
                    else:
                        st.code(json.dumps(block, indent=2, default=str),
                                language="json")
