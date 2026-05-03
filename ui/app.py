"""NAV Defect Detection System -- Streamlit entry point.

Run:
    streamlit run ui/app.py

The UI is a viewer over audit/agent_runs/. Fixture runs are present by
default so the demo works without API spend. The Run-Live page is the
only screen that consumes credits and is gated behind an explicit
acknowledgement.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from ui.styling import apply_enterprise_theme, page_header  # noqa: E402
from ui.data_loaders import (  # noqa: E402
    aggregate_metrics, load_all_runs,
)


st.set_page_config(
    page_title="NAV Defect Detection",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": None},
)
apply_enterprise_theme()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        """
        <div style="padding: 4px 0 14px 0; border-bottom: 1px solid #292524;
                    margin-bottom: 14px;">
          <div style="font-size: 0.72rem; color:#a8a29e;
                      text-transform: uppercase; letter-spacing: 0.08em;">
            Fund Administration
          </div>
          <div style="font-size: 1.05rem; color:#f5f5f4; font-weight: 600;">
            NAV Defect Detection
          </div>
          <div style="color:#a8a29e; font-size: 0.78rem; margin-top: 2px;">
            Pre-close NAV oversight
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="panel-meta" style="margin-bottom:6px;">Navigation</div>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Landing content (when user opens app.py directly)
# ---------------------------------------------------------------------------
page_header(
    "NAV Defect Detection",
    "Pre-close oversight for fund administration. "
    "Investigates each fund-day, surfaces defects, recommends actions.",
)

runs = load_all_runs()
metrics = aggregate_metrics(runs)

cols = st.columns(4)
with cols[0]:
    st.metric("Runs in audit log", f"{metrics['n_runs']:,d}")
with cols[1]:
    st.metric("Defects detected", f"{metrics['defects_total']:,d}")
with cols[2]:
    st.metric("NAV strikes blocked", f"{metrics['blocked']:,d}")
with cols[3]:
    avg = metrics["avg_confidence"]
    st.metric("Avg verdict confidence", f"{avg:.2f}" if avg is not None else "—")

st.markdown("---")

st.markdown(
    """
    <div class="panel">
      <div class="panel-title" style="margin-bottom: 8px;">Getting started</div>
      <div style="color:#d6d3d1; font-size: 0.92rem; line-height: 1.55;">
        <ul style="margin: 0; padding-left: 18px;">
          <li><strong>Dashboard</strong> &mdash; today's NAV strike status across the fund universe.</li>
          <li><strong>Defect Detail</strong> &mdash; evidence chain and audit trail for a single run.</li>
          <li><strong>Run Explorer</strong> &mdash; browse historical runs, filter by fund, severity, action.</li>
          <li><strong>Configuration</strong> &mdash; per-fund policy overrides and severity thresholds.</li>
          <li><strong>Run Live</strong> &mdash; invoke the agent against the warehouse (consumes API credits, gated).</li>
        </ul>
      </div>
    </div>

    <div class="panel">
      <div class="panel-title" style="margin-bottom: 8px;">About this build</div>
      <div style="color:#a8a29e; font-size: 0.85rem; line-height: 1.55;">
        Synthetic warehouse, synthetic fund universe, fixture-based audit
        trail. The Run Live screen is the only path that consumes external
        API credits. All other screens render pre-recorded
        <span class="mono">audit/agent_runs/*.json</span> records and work
        offline.
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
