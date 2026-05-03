"""Daily run dashboard: multi-fund overview for a chosen NAV date."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from ui.styling import (  # noqa: E402
    apply_enterprise_theme, page_header, severity_badge, action_badge,
    fmt_count,
)
from ui.data_loaders import (  # noqa: E402
    aggregate_metrics, latest_run_per_fund, load_all_runs, load_funds,
    runs_to_dashboard_table,
)


st.set_page_config(page_title="Dashboard", layout="wide")
apply_enterprise_theme()
page_header(
    "Daily Run Dashboard",
    "Per-fund NAV oversight status for the selected pricing date.",
)

# ---------------------------------------------------------------------------
# Date selector
# ---------------------------------------------------------------------------
runs = load_all_runs()
funds_df = load_funds()

# Default date: most recent fund-day in the audit log, or today.
all_dates = sorted({
    date.fromisoformat(r["as_of_date"][:10])
    for r in runs if r.get("as_of_date")
}, reverse=True)
default_date = all_dates[0] if all_dates else date.today()

cols = st.columns([2, 2, 8])
with cols[0]:
    selected_date = st.date_input(
        "NAV date", value=default_date,
        format="YYYY-MM-DD",
    )
with cols[1]:
    show_all_dates = st.toggle(
        "All dates (latest run per fund)", value=True,
        help="Off: only show runs from the selected date.",
    )

# Filter runs by date if requested.
if show_all_dates:
    relevant = runs
else:
    relevant = [
        r for r in runs
        if r.get("as_of_date") and
        date.fromisoformat(r["as_of_date"][:10]) == selected_date
    ]

# ---------------------------------------------------------------------------
# Aggregate metrics
# ---------------------------------------------------------------------------
m = aggregate_metrics(relevant)
mcols = st.columns(4)
with mcols[0]:
    st.metric("Total runs", f"{m['n_runs']:,d}")
with mcols[1]:
    st.metric("Defects detected", f"{m['defects_total']:,d}")
with mcols[2]:
    st.metric("NAV strikes blocked", f"{m['blocked']:,d}")
with mcols[3]:
    avg = m["avg_confidence"]
    st.metric("Avg confidence", f"{avg:.2f}" if avg is not None else "—")

st.markdown("---")

# ---------------------------------------------------------------------------
# Fund table
# ---------------------------------------------------------------------------
table = runs_to_dashboard_table(relevant, funds_df)

# Derive a sortable severity rank so the user can sort by gravity.
SEV_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "—": 0, "NONE": 0}
table["sev_rank"] = table["severity"].map(lambda s: SEV_RANK.get(s, 0))

# Sort by severity desc by default.
table = table.sort_values(
    by=["sev_rank", "fund_id"], ascending=[False, True],
).reset_index(drop=True)

st.markdown(
    '<div class="panel-meta" style="margin-bottom:6px;">Funds</div>',
    unsafe_allow_html=True,
)

# Render table with a click-to-detail button per row.
header_cols = st.columns([1.2, 2.5, 1.2, 1.2, 1.5, 1.6, 1.0, 0.9, 1.0])
for col, label in zip(
    header_cols,
    ["Fund", "Name", "NAV date", "Status", "Severity", "Action",
     "Defects", "Conf.", " "],
):
    col.markdown(f'<div class="panel-meta">{label}</div>', unsafe_allow_html=True)

st.markdown(
    '<div style="height:1px; background:#292524; margin: 4px 0 8px 0;"></div>',
    unsafe_allow_html=True,
)

if len(table) == 0:
    st.markdown(
        '<div class="dim" style="padding: 12px;">No runs match the current filter.</div>',
        unsafe_allow_html=True,
    )
else:
    for _, row in table.iterrows():
        cells = st.columns([1.2, 2.5, 1.2, 1.2, 1.5, 1.6, 1.0, 0.9, 1.0])
        sev = row["severity"]
        action = row["action"]
        cells[0].markdown(
            f'<span class="mono" style="color:#f5f5f4;">{row["fund_id"]}</span>',
            unsafe_allow_html=True,
        )
        cells[1].markdown(
            f'<span style="color:#d6d3d1;">{row["name"]}</span>',
            unsafe_allow_html=True,
        )
        cells[2].markdown(
            f'<span class="mono" style="color:#a8a29e;">'
            f'{row["as_of_date"][:10] if row["as_of_date"] else "—"}</span>',
            unsafe_allow_html=True,
        )
        status_color = {
            "complete": "#16a34a",
            "halted": "#b45309",
            "not_run": "#52525b",
        }.get(row["status"], "#52525b")
        cells[3].markdown(
            f'<span style="color:{status_color}; font-size:0.85rem;">'
            f'{row["status"]}</span>',
            unsafe_allow_html=True,
        )
        cells[4].markdown(
            severity_badge(sev) if sev not in ("—", "NONE") else
            '<span class="dim">—</span>',
            unsafe_allow_html=True,
        )
        cells[5].markdown(
            action_badge(action) if action != "—" else
            '<span class="dim">—</span>',
            unsafe_allow_html=True,
        )
        cells[6].markdown(fmt_count(int(row["defects"])), unsafe_allow_html=True)
        cells[7].markdown(
            f'<span class="mono numeric">{row["confidence"]:.2f}</span>'
            if row["confidence"] is not None else
            '<span class="dim">—</span>',
            unsafe_allow_html=True,
        )
        if row["run_id"]:
            if cells[8].button(
                "Open", key=f"open_{row['run_id']}",
                use_container_width=True,
            ):
                st.session_state["selected_run_id"] = row["run_id"]
                st.switch_page("pages/2_Defect_Detail.py")
        else:
            cells[8].markdown('<span class="dim">—</span>', unsafe_allow_html=True)
        st.markdown(
            '<div style="height:1px; background:#1c1917; margin: 6px 0;"></div>',
            unsafe_allow_html=True,
        )
