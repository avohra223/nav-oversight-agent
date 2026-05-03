"""Verdict card: the primary unit of information on the defect-detail page.

One card per Verdict. Shows defect type, severity, confidence, recommended
action, plain-English reasoning, and an expandable evidence chain.
"""
from __future__ import annotations

from typing import Any

import streamlit as st

from ..styling import (
    action_badge, confidence_bar, fmt_bps, mono, severity_badge,
)


def render_verdict_card(verdict: dict[str, Any], idx: int) -> None:
    sev = (verdict.get("severity") or "NONE").upper()
    conf = float(verdict.get("confidence") or 0.0)
    action = (verdict.get("recommended_action") or "LOG_ONLY").upper()
    defect_type = verdict.get("defect_type") or "no_defect"
    bps = verdict.get("bps_impact")

    st.markdown(
        f"""
<div class="panel">
  <div class="panel-header">
    <div>
      <span class="panel-title">{defect_type.replace('_', ' ').title()}</span>
      <span style="margin-left: 12px;">{severity_badge(sev)}</span>
    </div>
    <div class="panel-meta">verdict #{idx}</div>
  </div>
  <div style="display: flex; gap: 28px; margin-bottom: 12px; flex-wrap: wrap;">
    <div>
      <div class="panel-meta">Confidence</div>
      <div style="margin-top: 4px;">{confidence_bar(conf)}</div>
    </div>
    <div>
      <div class="panel-meta">Recommended Action</div>
      <div style="margin-top: 4px;">{action_badge(action)}</div>
    </div>
    <div>
      <div class="panel-meta">NAV Impact</div>
      <div style="margin-top: 4px;">{fmt_bps(bps)}</div>
    </div>
    <div>
      <div class="panel-meta">Defect Code</div>
      <div style="margin-top: 4px;">{mono(defect_type)}</div>
    </div>
  </div>
  <div style="background: #0c0a09; border-left: 3px solid #44403c;
              padding: 12px 14px; margin-top: 6px; color: #d6d3d1;
              font-size: 0.92rem; line-height: 1.55;">
    {verdict.get("reasoning") or ""}
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    # Evidence list (expandable)
    evidence = verdict.get("evidence") or []
    if evidence:
        with st.expander(f"Evidence ({len(evidence)} items)", expanded=False):
            for i, e in enumerate(evidence, 1):
                _render_evidence_item(e, i)

    # Action controls
    cols = st.columns([1, 1, 2, 1])
    with cols[0]:
        if st.button("Approve", key=f"approve_{idx}", use_container_width=True):
            st.toast(f"Verdict {idx} approved", icon=None)
    with cols[1]:
        if st.button("Reject", key=f"reject_{idx}", use_container_width=True,
                     type="secondary"):
            st.session_state[f"reject_open_{idx}"] = True
    with cols[2]:
        new_sev = st.selectbox(
            "Override severity",
            ["—", "LOW", "MEDIUM", "HIGH", "CRITICAL"],
            key=f"override_{idx}",
            label_visibility="collapsed",
        )
    with cols[3]:
        if st.button("Escalate", key=f"escalate_{idx}", use_container_width=True,
                     type="secondary"):
            st.toast(f"Verdict {idx} escalated to team lead", icon=None)

    if st.session_state.get(f"reject_open_{idx}"):
        with st.container(border=True):
            reason = st.text_input(
                "Reason for rejection",
                key=f"reject_reason_{idx}",
                placeholder="Why is this verdict incorrect?",
            )
            cols2 = st.columns([1, 1, 6])
            with cols2[0]:
                if st.button("Submit", key=f"reject_submit_{idx}", type="primary"):
                    st.toast(f"Verdict {idx} rejected: {reason or '(no reason)'}")
                    st.session_state[f"reject_open_{idx}"] = False
            with cols2[1]:
                if st.button("Cancel", key=f"reject_cancel_{idx}"):
                    st.session_state[f"reject_open_{idx}"] = False


def _render_evidence_item(e: dict[str, Any], i: int) -> None:
    src_table = e.get("source_table") or "—"
    src_key = e.get("source_key") or {}
    src_fields = e.get("source_fields") or []
    observed = e.get("observed_value")
    expected = e.get("expected_value")

    st.markdown(
        f"""
<div style="background: #0c0a09; border: 1px solid #292524; border-radius: 4px;
            padding: 10px 12px; margin-bottom: 8px;">
  <div style="display: flex; justify-content: space-between; gap: 10px;">
    <div style="color: #e7e5e4; font-size: 0.92rem; line-height: 1.45;">
      {e.get("description") or ""}
    </div>
    <div class="panel-meta" style="white-space: nowrap;">item {i}</div>
  </div>
  <div style="display: flex; gap: 22px; margin-top: 8px; flex-wrap: wrap;
              font-size: 0.78rem;">
    <div><span class="panel-meta">source</span>
         <span class="mono" style="color:#d6d3d1; margin-left:6px;">{src_table}</span></div>
    {(f'<div><span class="panel-meta">key</span>'
       f'<span class="mono" style="color:#d6d3d1; margin-left:6px;">'
       f'{_compact_dict(src_key)}</span></div>') if src_key else ''}
    {(f'<div><span class="panel-meta">fields</span>'
       f'<span class="mono" style="color:#d6d3d1; margin-left:6px;">'
       f'{", ".join(src_fields)}</span></div>') if src_fields else ''}
  </div>
  <div style="display: flex; gap: 22px; margin-top: 6px; font-size: 0.82rem;">
    <div><span class="panel-meta">observed</span>
         <span class="mono" style="color:#fef3c7; margin-left:6px;">
         {_compact(observed)}</span></div>
    {(f'<div><span class="panel-meta">expected</span>'
       f'<span class="mono" style="color:#bbf7d0; margin-left:6px;">'
       f'{_compact(expected)}</span></div>') if expected is not None else ''}
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def _compact(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, dict):
        return _compact_dict(v)
    if isinstance(v, float):
        if abs(v) < 1e-3 or abs(v) >= 1e9:
            return f"{v:.4g}"
        return f"{v:,.4f}".rstrip("0").rstrip(".")
    if isinstance(v, int):
        return f"{v:,d}"
    return str(v)


def _compact_dict(d: dict) -> str:
    return "{" + ", ".join(f"{k}={_compact(v)}" for k, v in d.items()) + "}"
