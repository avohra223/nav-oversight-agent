"""Run Live: invoke the agent against the warehouse. Consumes API credits.

This is the only page in the app that calls the Anthropic API. Gated
behind an explicit acknowledgement checkbox; the run button is disabled
until the user confirms understanding of the cost.
"""
from __future__ import annotations

import os
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from ui.styling import apply_enterprise_theme, page_header  # noqa: E402
from ui.data_loaders import load_funds  # noqa: E402


MODEL_INFO = {
    "claude-opus-4-7": {
        "label": "Opus 4.7 (most capable)",
        "cost_estimate": "approximately 1.50 to 2.50 USD per run",
        "input_per_mtok": 15.0,
        "output_per_mtok": 75.0,
    },
    "claude-sonnet-4-6": {
        "label": "Sonnet 4.6 (balanced)",
        "cost_estimate": "approximately 0.40 to 0.80 USD per run",
        "input_per_mtok": 3.0,
        "output_per_mtok": 15.0,
    },
    "claude-haiku-4-5-20251001": {
        "label": "Haiku 4.5 (fastest, cheapest)",
        "cost_estimate": "approximately 0.10 USD per run",
        "input_per_mtok": 1.0,
        "output_per_mtok": 5.0,
    },
}


st.set_page_config(page_title="Run Live", layout="wide")
apply_enterprise_theme()
page_header(
    "Run Live",
    "Invoke the agent against the warehouse. Each run consumes external API credits.",
)


# ---------------------------------------------------------------------------
# Cost / credit warning
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div style="background: #422006; border: 1px solid #b45309;
                border-left: 4px solid #b45309; border-radius: 3px;
                padding: 14px 18px; color: #fef3c7; margin-bottom: 16px;">
      <div style="font-weight: 600; font-size: 0.95rem; margin-bottom: 4px;">
        Live agent runs charge your Anthropic API account.
      </div>
      <div style="font-size: 0.88rem; line-height: 1.5;">
        The other pages in this application render pre-recorded audit
        records and consume no external resources. This page invokes
        the agent against the live warehouse and bills your API key per
        token. Use it only for a single intentional investigation or to
        record a fixture.
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# API key check
# ---------------------------------------------------------------------------
api_key_set = bool(os.environ.get("ANTHROPIC_API_KEY"))
key_cols = st.columns([2, 6])
with key_cols[0]:
    if api_key_set:
        st.markdown(
            '<div style="color:#4ade80;">ANTHROPIC_API_KEY is set</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="color:#f87171;">ANTHROPIC_API_KEY is NOT set</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "Export the env var in your shell before launching streamlit, "
            "or use the other pages with fixture data."
        )

st.markdown("---")

# ---------------------------------------------------------------------------
# Form
# ---------------------------------------------------------------------------
funds_df = load_funds()
fund_ids = funds_df["fund_id"].tolist()

cols = st.columns([2, 2, 2, 4])
with cols[0]:
    fund_id = st.selectbox("Fund", fund_ids)
with cols[1]:
    as_of = st.date_input("NAV date", value=date(2026, 4, 2),
                          format="YYYY-MM-DD")
with cols[2]:
    share_class = st.text_input("Share class (optional)", value="",
                                placeholder="leave empty for fund-level")
with cols[3]:
    model_id = st.selectbox(
        "Model",
        list(MODEL_INFO.keys()),
        format_func=lambda m: MODEL_INFO[m]["label"],
    )

info = MODEL_INFO[model_id]
st.markdown(
    f"""
    <div class="panel">
      <div class="panel-title">Estimated cost</div>
      <div style="color:#d6d3d1; font-size: 0.92rem; margin-top: 6px;">
        Selected model: <span class="mono">{model_id}</span>.
        Cost: <strong>{info['cost_estimate']}</strong>
        (input <span class="mono">{info['input_per_mtok']:.2f}</span>/M,
         output <span class="mono">{info['output_per_mtok']:.2f}</span>/M).
        Prompt caching is enabled and reduces repeat-run cost materially.
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


ack = st.checkbox(
    "I understand this will charge my Anthropic API account.",
    value=False,
)

run_disabled = not (ack and api_key_set)
run_clicked = st.button(
    "Run agent now",
    type="primary",
    disabled=run_disabled,
    use_container_width=False,
)
if run_disabled:
    st.caption(
        "Run is disabled until both the acknowledgement is checked and "
        "the API key is available in the environment."
    )

# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------
if run_clicked:
    from agent import run_agent  # imported here to avoid cost on page load

    placeholder = st.empty()
    placeholder.info("Invoking agent. This typically takes 30-90 seconds.")
    log_block = st.empty()

    started = datetime.utcnow()
    try:
        run = run_agent(
            fund_id=fund_id,
            as_of_date=as_of,
            share_class=share_class or None,
            model=model_id,
        )
        finished = datetime.utcnow()
        placeholder.success(
            f"Run complete in {(finished - started).total_seconds():.1f} s. "
            f"Audit record: audit/agent_runs/{run.run_id}.json"
        )
        st.session_state["selected_run_id"] = run.run_id

        cols2 = st.columns([2, 8])
        with cols2[0]:
            if st.button("Open in Defect Detail",
                         type="primary",
                         use_container_width=True):
                st.switch_page("pages/2_Defect_Detail.py")

        # Quick verdict summary
        for v in run.verdicts:
            st.markdown(
                f"- **{v.defect_type}** &middot; severity "
                f"`{v.severity}` &middot; conf {v.confidence:.2f} &middot; "
                f"{v.recommended_action}"
            )

    except RuntimeError as e:
        if "ANTHROPIC_API_KEY" in str(e):
            placeholder.error(
                "ANTHROPIC_API_KEY is missing. Set it in your shell and restart."
            )
        else:
            placeholder.error(f"Agent error: {e}")
            log_block.code(traceback.format_exc())
    except Exception as e:
        placeholder.error(f"Run failed: {type(e).__name__}: {e}")
        log_block.code(traceback.format_exc())
