"""Enterprise theme for the Streamlit UI.

Muted slate/stone palette, no neon, no emoji. Typography uses system font
stacks so the app works offline (no CDN font fetches).

Reference aesthetics: BlackRock Aladdin, BNP Paribas internal tools, State
Street operational dashboards. Dense, functional, trustworthy.
"""
from __future__ import annotations

import streamlit as st


# Severity -> hex colour. Picked for accessible contrast on a dark slate
# background and to look professional rather than alarming.
SEVERITY_COLOR = {
    "CRITICAL": "#9f1239",   # rose-800
    "HIGH":     "#b45309",   # amber-700
    "MEDIUM":   "#0369a1",   # sky-700
    "LOW":      "#475569",   # slate-600
    "NONE":     "#16a34a",   # green-600
}

ACTION_COLOR = {
    "BLOCK_NAV":      "#9f1239",
    "URGENT_REVIEW":  "#b45309",
    "REVIEW_QUEUE":   "#0369a1",
    "LOG_ONLY":       "#475569",
    "AUTO_SIGN_OFF":  "#16a34a",
}


def apply_enterprise_theme() -> None:
    """Inject the global stylesheet. Call at the top of every page."""
    st.markdown(
        """
<style>
/* --- Hide Streamlit chrome (menu, deploy button, footer) ----------------- */
#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDecoration"] { display: none; }
.stDeployButton { display: none; }

/* --- Typography (system fonts only; no CDN) ------------------------------ */
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                 "Helvetica Neue", Helvetica, Arial, sans-serif !important;
    color: #e7e5e4;
}
.mono {
    font-family: "JetBrains Mono", "Cascadia Code", Consolas,
                 "Courier New", Menlo, Monaco, monospace !important;
    font-feature-settings: "tnum" 1;
}
.numeric { font-variant-numeric: tabular-nums; }

/* --- Backgrounds --------------------------------------------------------- */
.stApp {
    background: #0c0a09;     /* stone-950 */
    color: #e7e5e4;          /* stone-200 */
}
[data-testid="stSidebar"] {
    background: #1c1917;     /* stone-900 */
    border-right: 1px solid #292524;
}
[data-testid="stSidebar"] * { color: #d6d3d1; }
[data-testid="stSidebar"] .st-emotion-cache-pkbazv {
    color: #a8a29e !important;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

/* --- Headings ------------------------------------------------------------ */
h1, h2, h3, h4 {
    color: #f5f5f4 !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em;
}
h1 { font-size: 1.65rem !important; margin-bottom: 0.5rem !important; }
h2 { font-size: 1.25rem !important; }
h3 { font-size: 1.05rem !important; color: #d6d3d1 !important; }

/* --- Cards / panels ----------------------------------------------------- */
.panel {
    background: #1c1917;
    border: 1px solid #292524;
    border-radius: 4px;
    padding: 16px 18px;
    margin-bottom: 12px;
}
.panel-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 10px; padding-bottom: 8px;
    border-bottom: 1px solid #292524;
}
.panel-title {
    color: #f5f5f4;
    font-weight: 600;
    font-size: 0.95rem;
    letter-spacing: -0.005em;
}
.panel-meta {
    color: #a8a29e;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

/* --- Severity badges ---------------------------------------------------- */
.badge {
    display: inline-block;
    padding: 2px 9px;
    border-radius: 3px;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    white-space: nowrap;
}
.badge-CRITICAL { background: #9f1239; color: #fff1f2; }
.badge-HIGH     { background: #b45309; color: #fffbeb; }
.badge-MEDIUM   { background: #0369a1; color: #f0f9ff; }
.badge-LOW      { background: #475569; color: #f1f5f9; }
.badge-NONE     { background: #166534; color: #f0fdf4; }

.badge-action-BLOCK_NAV     { background: #9f1239; color: #fff1f2; }
.badge-action-URGENT_REVIEW { background: #b45309; color: #fffbeb; }
.badge-action-REVIEW_QUEUE  { background: #0369a1; color: #f0f9ff; }
.badge-action-LOG_ONLY      { background: #475569; color: #f1f5f9; }
.badge-action-AUTO_SIGN_OFF { background: #166534; color: #f0fdf4; }

/* --- Confidence bar ----------------------------------------------------- */
.confidence-bar {
    display: inline-block;
    height: 8px;
    background: #292524;
    border-radius: 2px;
    overflow: hidden;
    width: 120px;
    vertical-align: middle;
    margin-left: 6px;
}
.confidence-fill {
    height: 100%;
    background: #94a3b8;
}

/* --- Tables ------------------------------------------------------------- */
[data-testid="stDataFrame"] {
    border: 1px solid #292524 !important;
    border-radius: 4px !important;
}
[data-testid="stDataFrame"] * {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                 "Helvetica Neue", Helvetica, Arial, sans-serif !important;
    font-size: 0.85rem !important;
}

/* --- Buttons ------------------------------------------------------------ */
button[kind="primary"] {
    background: #1d4ed8 !important;
    border-color: #1e3a8a !important;
    color: #f5f5f4 !important;
    font-weight: 600 !important;
}
button[kind="secondary"] {
    background: #1c1917 !important;
    border-color: #44403c !important;
    color: #d6d3d1 !important;
}

/* --- Metrics ------------------------------------------------------------ */
[data-testid="stMetric"] {
    background: #1c1917;
    border: 1px solid #292524;
    border-radius: 4px;
    padding: 14px 16px;
}
[data-testid="stMetricLabel"] {
    color: #a8a29e !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.72rem !important;
    font-weight: 500 !important;
}
[data-testid="stMetricValue"] {
    color: #f5f5f4 !important;
    font-weight: 600 !important;
    font-variant-numeric: tabular-nums !important;
}

/* --- Inputs / select ---------------------------------------------------- */
[data-testid="stTextInput"] input, [data-testid="stDateInput"] input {
    background: #1c1917 !important;
    color: #e7e5e4 !important;
    border-color: #292524 !important;
}

/* --- Misc --------------------------------------------------------------- */
.dim { color: #a8a29e; }
.numeric-positive { color: #4ade80; }
.numeric-negative { color: #f87171; }
hr { border-color: #292524 !important; }
.stTabs [data-baseweb="tab-list"] { background: transparent; }
.stTabs [data-baseweb="tab"] { color: #a8a29e; }
.stTabs [aria-selected="true"] { color: #f5f5f4; }
</style>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str | None = None) -> None:
    st.markdown(
        f"""
        <div style="margin-bottom: 18px; padding-bottom: 10px;
                    border-bottom: 1px solid #292524;">
          <div style="font-size: 0.72rem; color: #a8a29e;
                      text-transform: uppercase; letter-spacing: 0.08em;">
            NAV Defect Detection System
          </div>
          <div style="font-size: 1.4rem; color: #f5f5f4; font-weight: 600;
                      margin-top: 2px;">{title}</div>
          {f'<div style="color: #a8a29e; font-size: 0.92rem; margin-top: 2px;">{subtitle}</div>' if subtitle else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def severity_badge(severity: str) -> str:
    """Return inline HTML for a severity badge."""
    severity = severity.upper()
    return f'<span class="badge badge-{severity}">{severity}</span>'


def action_badge(action: str) -> str:
    action = action.upper()
    return f'<span class="badge badge-action-{action}">{action.replace("_", " ")}</span>'


def confidence_bar(confidence: float) -> str:
    pct = max(0, min(100, int(confidence * 100)))
    return (
        f'<span class="mono" style="color:#a8a29e;">{confidence:.2f}</span>'
        f'<span class="confidence-bar"><span class="confidence-fill" '
        f'style="width:{pct}%;"></span></span>'
    )


def mono(text: str) -> str:
    return f'<span class="mono">{text}</span>'


def fmt_bps(value: float | None) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    color = "numeric-negative" if value < 0 else "numeric-positive"
    return f'<span class="mono numeric {color}">{sign}{value:.1f} bps</span>'


def fmt_money(value: float | None, ccy: str = "USD") -> str:
    if value is None:
        return "—"
    return f'<span class="mono numeric">{value:,.2f} {ccy}</span>'


def fmt_count(value: int | None) -> str:
    if value is None:
        return "—"
    return f'<span class="mono numeric">{value:,d}</span>'
