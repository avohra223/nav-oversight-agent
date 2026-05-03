"""Configuration: edit config/policies.yaml from the UI."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from ui.styling import apply_enterprise_theme, page_header  # noqa: E402


CONFIG_PATH = ROOT / "config" / "policies.yaml"

SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL", "NONE"]
ACTIONS = [
    "AUTO_SIGN_OFF", "LOG_ONLY", "REVIEW_QUEUE", "URGENT_REVIEW", "BLOCK_NAV",
]
DEFECT_TYPES = [
    "single_stock_shock", "fx_cutoff_mismatch", "missed_corp_action",
    "stale_price", "stale_hwm_perf_fee", "trade_wrong_side",
    "missed_coupon_accrual", "subscription_pre_cutoff", "wrong_wht",
    "class_fee_misallocation",
]


st.set_page_config(page_title="Configuration", layout="wide")
apply_enterprise_theme()
page_header(
    "Policy Configuration",
    "Per-fund overrides and default routing rules. "
    "Saved to config/policies.yaml; the agent reads on import.",
)

# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
def _load() -> dict:
    if CONFIG_PATH.exists():
        return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return {"defaults": [], "fund_overrides": []}


def _save(cfg: dict) -> None:
    CONFIG_PATH.write_text(
        yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


cfg = _load()
defaults = cfg.get("defaults", []) or []
overrides = cfg.get("fund_overrides", []) or []

# ---------------------------------------------------------------------------
# Tabs: Defaults, Per-fund overrides, Raw YAML
# ---------------------------------------------------------------------------
tab_defaults, tab_overrides, tab_raw = st.tabs([
    "Default rules", "Fund overrides", "Raw YAML",
])


def _validate(rule: dict, idx: int, label: str) -> list[str]:
    errors: list[str] = []
    if not rule.get("rule_id"):
        errors.append(f"{label} #{idx}: rule_id is required")
    when = rule.get("when") or {}
    sev = when.get("severity_in") or []
    for s in sev:
        if s not in SEVERITIES:
            errors.append(f"{label} #{idx}: severity '{s}' not in {SEVERITIES}")
    mc = when.get("min_confidence")
    if mc is not None and not (0.0 <= float(mc) <= 1.0):
        errors.append(f"{label} #{idx}: min_confidence must be 0..1, got {mc}")
    if rule.get("action") and rule["action"] not in ACTIONS:
        errors.append(
            f"{label} #{idx}: action '{rule['action']}' not in {ACTIONS}"
        )
    return errors


with tab_defaults:
    st.markdown(
        '<div class="panel-meta" style="margin-bottom:6px;">'
        'Default rules apply when no fund override matches.'
        '</div>',
        unsafe_allow_html=True,
    )
    new_defaults: list[dict] = []
    for i, rule in enumerate(defaults):
        with st.container(border=True):
            cols = st.columns([2, 2, 2, 2, 2])
            with cols[0]:
                rule_id = st.text_input(
                    "rule_id", value=rule.get("rule_id", ""),
                    key=f"def_id_{i}",
                )
            with cols[1]:
                sev_in = st.multiselect(
                    "severity_in",
                    SEVERITIES,
                    default=(rule.get("when", {}) or {}).get("severity_in", []),
                    key=f"def_sev_{i}",
                )
            with cols[2]:
                mc = st.number_input(
                    "min_confidence",
                    min_value=0.0, max_value=1.0, step=0.05,
                    value=float((rule.get("when", {}) or {}).get("min_confidence", 0.0)),
                    key=f"def_mc_{i}",
                )
            with cols[3]:
                act = st.selectbox(
                    "action", ACTIONS,
                    index=ACTIONS.index(rule.get("action", "LOG_ONLY"))
                    if rule.get("action") in ACTIONS else 1,
                    key=f"def_act_{i}",
                )
            with cols[4]:
                esc = st.text_input(
                    "escalate_to",
                    value=rule.get("escalate_to") or "",
                    key=f"def_esc_{i}",
                )
            ch = st.text_input(
                "notification_channel",
                value=rule.get("notification_channel") or "",
                key=f"def_ch_{i}",
            )
            new_defaults.append({
                "rule_id": rule_id,
                "when": {"severity_in": sev_in, "min_confidence": mc},
                "action": act,
                "escalate_to": esc or None,
                "notification_channel": ch or None,
            })


with tab_overrides:
    st.markdown(
        '<div class="panel-meta" style="margin-bottom:6px;">'
        'Per-fund overrides resolved before defaults. '
        'Most-specific match wins.'
        '</div>',
        unsafe_allow_html=True,
    )
    new_overrides: list[dict] = []
    for i, rule in enumerate(overrides):
        with st.container(border=True):
            cols = st.columns([1.6, 1.6, 1.8, 1.6, 1.4, 1.6])
            with cols[0]:
                rule_id = st.text_input(
                    "rule_id", value=rule.get("rule_id", ""),
                    key=f"ov_id_{i}",
                )
            with cols[1]:
                fund_id = st.text_input(
                    "fund_id", value=rule.get("fund_id") or "",
                    key=f"ov_fund_{i}",
                )
            with cols[2]:
                dtype = st.selectbox(
                    "defect_type",
                    ["(any)"] + DEFECT_TYPES,
                    index=(DEFECT_TYPES.index(rule["defect_type"]) + 1)
                          if rule.get("defect_type") in DEFECT_TYPES else 0,
                    key=f"ov_dt_{i}",
                )
            with cols[3]:
                sev_in = st.multiselect(
                    "severity_in",
                    SEVERITIES,
                    default=(rule.get("when", {}) or {}).get("severity_in", []),
                    key=f"ov_sev_{i}",
                )
            with cols[4]:
                mc = st.number_input(
                    "min_confidence",
                    min_value=0.0, max_value=1.0, step=0.05,
                    value=float((rule.get("when", {}) or {}).get("min_confidence", 0.0)),
                    key=f"ov_mc_{i}",
                )
            with cols[5]:
                act = st.selectbox(
                    "action", ACTIONS,
                    index=ACTIONS.index(rule.get("action", "LOG_ONLY"))
                    if rule.get("action") in ACTIONS else 1,
                    key=f"ov_act_{i}",
                )
            esc = st.text_input(
                "escalate_to",
                value=rule.get("escalate_to") or "",
                key=f"ov_esc_{i}",
            )
            ch = st.text_input(
                "notification_channel",
                value=rule.get("notification_channel") or "",
                key=f"ov_ch_{i}",
            )
            new_overrides.append({
                "rule_id": rule_id,
                "fund_id": fund_id,
                **({"defect_type": dtype} if dtype != "(any)" else {}),
                "when": {"severity_in": sev_in, "min_confidence": mc},
                "action": act,
                "escalate_to": esc or None,
                "notification_channel": ch or None,
            })


with tab_raw:
    st.code(
        yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False),
        language="yaml",
    )

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
st.markdown("---")
errors: list[str] = []
for i, r in enumerate(new_defaults):
    errors.extend(_validate(r, i, "default"))
for i, r in enumerate(new_overrides):
    errors.extend(_validate(r, i, "override"))

cols = st.columns([1, 1, 6])
with cols[0]:
    save_disabled = bool(errors)
    if st.button(
        "Save changes",
        type="primary", disabled=save_disabled, use_container_width=True,
    ):
        new_cfg = {"defaults": new_defaults, "fund_overrides": new_overrides}
        try:
            _save(new_cfg)
            # Reload in the policies module so the change takes effect.
            try:
                from agent.policies import reload_policies
                reload_policies(CONFIG_PATH)
            except Exception:
                pass
            st.success("Saved policies.yaml")
        except Exception as e:
            st.error(f"Save failed: {e}")
with cols[1]:
    if st.button("Reload from disk", use_container_width=True, type="secondary"):
        st.rerun()

if errors:
    st.error("Validation errors:\n\n" + "\n".join(f"- {e}" for e in errors))
