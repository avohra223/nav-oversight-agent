"""Generate agent/prompts/tool_descriptions.md from the tool registry.

Run after any change to dispatcher.py / tool docstrings to refresh the
human-readable inventory. The agent itself receives tool definitions via
the tools= parameter to the API; this file is for human reference and
documentation.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import inspect
import json

from agent.dispatcher import TOOL_REGISTRY  # noqa: E402


CATEGORY_OF = {
    "get_funds": "A. Reference",
    "get_share_classes": "A. Reference",
    "get_fund_domicile": "A. Reference",
    "get_instruments": "A. Reference",
    "get_treaty_rate": "A. Reference",
    "get_fund_calendar": "A. Reference",
    "get_holdings": "B. Positions",
    "get_holdings_history": "B. Positions",
    "get_trades": "B. Positions",
    "get_cash": "B. Positions",
    "get_capstock": "B. Positions",
    "get_price_series": "C. Market data",
    "get_price_around_date": "C. Market data",
    "get_fx_rate": "C. Market data",
    "get_fx_rates_all_snaps": "C. Market data",
    "get_bond_accruals": "C. Market data",
    "get_corporate_actions": "D. Income / corporate actions",
    "get_dividend_receipts": "D. Income / corporate actions",
    "get_nav_history": "E. NAV / fees",
    "get_fee_accruals": "E. NAV / fees",
    "compute_implied_dividend_return": "F. Computation (no DB)",
    "compute_implied_wht_rate": "F. Computation (no DB)",
    "compute_expected_coupon_accrual": "F. Computation (no DB)",
    "compute_perf_fee": "F. Computation (no DB)",
    "compute_attribution": "F. Computation (no DB)",
    "detect_flat_run_in_series": "F. Computation (no DB)",
    "compute_nav_move_bps": "F. Computation (no DB)",
}


def main() -> None:
    out = ROOT / "agent" / "prompts" / "tool_descriptions.md"
    lines = [
        "# Tool descriptions",
        "",
        "Auto-generated from `agent/dispatcher.TOOL_REGISTRY` and the underlying",
        "tool docstrings. Re-run `python scripts/generate_tool_descriptions.py`",
        "after any change to a tool signature, docstring, or schema.",
        "",
        "The agent receives these tools via the `tools=` parameter on each",
        "Anthropic API call. This file is for human reference.",
        "",
    ]

    by_cat: dict[str, list[str]] = {}
    for name, spec in TOOL_REGISTRY.items():
        cat = CATEGORY_OF.get(name, "Z. Other")
        by_cat.setdefault(cat, []).append(name)

    # Add compute_attribution which is in TOOL_REGISTRY only via direct call?
    # It's not currently registered for the agent because it requires complex
    # holding/price input. Document if missing.
    for cat in sorted(by_cat):
        lines.append(f"## {cat}")
        lines.append("")
        for name in sorted(by_cat[cat]):
            spec = TOOL_REGISTRY[name]
            lines.append(f"### `{name}`")
            lines.append("")
            lines.append(spec["description"])
            lines.append("")
            schema_str = json.dumps(spec["input_schema"], indent=2)
            lines.append("Input schema:")
            lines.append("```json")
            lines.append(schema_str)
            lines.append("```")
            lines.append("")
        lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({len(TOOL_REGISTRY)} tools)")


if __name__ == "__main__":
    main()
