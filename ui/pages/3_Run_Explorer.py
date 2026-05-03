"""Run explorer: filter and browse historical runs."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from io import StringIO
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from ui.styling import apply_enterprise_theme, page_header  # noqa: E402
from ui.data_loaders import load_all_runs, runs_to_explorer_table  # noqa: E402


st.set_page_config(page_title="Run Explorer", layout="wide")
apply_enterprise_theme()
page_header(
    "Run Explorer",
    "Every recorded investigation. Filter, sort, export.",
)

runs = load_all_runs()
df = runs_to_explorer_table(runs)

if df.empty:
    st.info("No runs in the audit log. Generate fixtures or record a live run first.")
    st.stop()

# Filters
fcols = st.columns([1.5, 1.5, 1.5, 1.5, 1.5, 1])
with fcols[0]:
    funds = ["(all)"] + sorted(df["fund_id"].dropna().unique().tolist())
    fund_sel = st.selectbox("Fund", funds)
with fcols[1]:
    sevs = ["(all)", "CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE"]
    sev_sel = st.selectbox("Severity", sevs)
with fcols[2]:
    types = ["(all)"] + sorted(df["defect_type"].dropna().unique().tolist())
    type_sel = st.selectbox("Defect type", types)
with fcols[3]:
    actions = ["(all)"] + sorted(df["action"].dropna().unique().tolist())
    act_sel = st.selectbox("Action", actions)
with fcols[4]:
    # Date range filter: default to last 12 months covering the warehouse window.
    parsed_dates = []
    for d in df["as_of_date"].dropna():
        try:
            parsed_dates.append(date.fromisoformat(str(d)[:10]))
        except (ValueError, TypeError):
            pass
    if parsed_dates:
        min_d, max_d = min(parsed_dates), max(parsed_dates)
    else:
        max_d = date.today()
        min_d = max_d - timedelta(days=180)
    range_sel = st.date_input(
        "Date range", value=(min_d, max_d),
        format="YYYY-MM-DD",
    )
with fcols[5]:
    st.markdown("&nbsp;", unsafe_allow_html=True)
    if st.button("Reset", use_container_width=True, type="secondary"):
        st.rerun()

# Apply filters
mask = pd.Series(True, index=df.index)
if fund_sel != "(all)":
    mask &= df["fund_id"] == fund_sel
if sev_sel != "(all)":
    mask &= df["severity"] == sev_sel
if type_sel != "(all)":
    mask &= df["defect_type"] == type_sel
if act_sel != "(all)":
    mask &= df["action"] == act_sel
if isinstance(range_sel, tuple) and len(range_sel) == 2:
    start, end = range_sel
    def _within(d_str):
        try:
            d = date.fromisoformat(str(d_str)[:10])
            return start <= d <= end
        except (ValueError, TypeError):
            return False
    mask &= df["as_of_date"].apply(_within)

filtered = df[mask].reset_index(drop=True)

# Top metrics
mcols = st.columns(4)
mcols[0].metric("Runs (filtered)", f"{len(filtered):,d}")
mcols[1].metric(
    "Defects",
    f"{(filtered['defect_type'] != 'no_defect').sum():,d}"
    if not filtered.empty else "0",
)
mcols[2].metric(
    "BLOCK_NAV",
    f"{(filtered['action'] == 'BLOCK_NAV').sum():,d}"
    if not filtered.empty else "0",
)
mcols[3].metric(
    "URGENT_REVIEW",
    f"{(filtered['action'] == 'URGENT_REVIEW').sum():,d}"
    if not filtered.empty else "0",
)

st.markdown("---")

# Table (Streamlit's column sort is built in)
display = filtered.copy()
display["as_of_date"] = display["as_of_date"].apply(lambda x: str(x)[:10] if x else "")
display["latency_s"] = display["latency_s"].round(1)
display["confidence"] = display["confidence"].apply(
    lambda x: round(float(x), 2) if x is not None else None
)
display["tokens_total"] = display["tokens_total"].astype(int)

st.dataframe(
    display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "run_id": st.column_config.TextColumn("Run ID", width="medium"),
        "fund_id": st.column_config.TextColumn("Fund", width="small"),
        "as_of_date": st.column_config.TextColumn("NAV date", width="small"),
        "share_class": st.column_config.TextColumn("Class", width="small"),
        "severity": st.column_config.TextColumn("Severity", width="small"),
        "defect_type": st.column_config.TextColumn("Defect type", width="medium"),
        "action": st.column_config.TextColumn("Action", width="small"),
        "confidence": st.column_config.NumberColumn(
            "Conf.", format="%.2f", width="small",
        ),
        "iterations": st.column_config.NumberColumn("Iter", width="small"),
        "tokens_total": st.column_config.NumberColumn(
            "Tokens", format="%d", width="small",
        ),
        "latency_s": st.column_config.NumberColumn(
            "Latency (s)", format="%.1f", width="small",
        ),
        "model": st.column_config.TextColumn("Model", width="medium"),
        "prompt_version": st.column_config.TextColumn("Prompt", width="small"),
        "started_at": st.column_config.TextColumn("Started", width="medium"),
    },
)

# Open + export controls
ocols = st.columns([2, 2, 8])
with ocols[0]:
    selected_run = st.selectbox(
        "Open run",
        ["(none)"] + filtered["run_id"].tolist(),
        label_visibility="collapsed",
    )
    if selected_run != "(none)":
        if st.button("Open", use_container_width=True, type="primary"):
            st.session_state["selected_run_id"] = selected_run
            st.switch_page("pages/2_Defect_Detail.py")

with ocols[1]:
    csv_buf = StringIO()
    display.to_csv(csv_buf, index=False)
    st.download_button(
        "Export CSV",
        data=csv_buf.getvalue(),
        file_name="nav_oversight_runs.csv",
        mime="text/csv",
        use_container_width=True,
        type="secondary",
    )
