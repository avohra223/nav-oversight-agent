"""Generate synthetic AgentRun JSON files that look like real agent runs.

Each fixture corresponds to one of the 10 seeded defects (or a clean
fund-day for variety). The fixture exercises real Phase 2 tools to
populate tool_result blocks with authentic data shapes; only the LLM
narration and final verdicts are scripted.

When real agent runs are recorded later (with API credits), the fixture
files at `audit/agent_runs/fixture_*.json` are replaced 1:1 -- the UI
contract is identical.

Run:
    python scripts/generate_fixture_runs.py
"""
from __future__ import annotations

import json
import sys
import uuid
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from agent.dispatcher import dispatch  # noqa: E402
from agent.policies import apply_policy  # noqa: E402
from agent.schemas import (  # noqa: E402
    AgentRun, EvidenceItem, PolicyAction, ToolCall, TokenUsage, Verdict,
    to_json_dict,
)
from agent.versioning import prompt_version  # noqa: E402


FIXTURES_DIR = ROOT / "audit" / "agent_runs"
MANIFEST_PATH = FIXTURES_DIR / "fixtures_manifest.json"

# Use a stable date for fixture creation timestamps.
FIXTURE_CREATED = datetime(2026, 5, 2, 14, 0, 0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _toolu_id(i: int) -> str:
    return f"toolu_fixture_{i:04d}"


def _make_run_id(fund_id: str, as_of: date, suffix: str) -> str:
    base = FIXTURE_CREATED.strftime("%Y%m%dT%H%M%S")
    return f"fixture_{base}_{fund_id}_{as_of.isoformat()}_{suffix}"


@dataclass
class _Step:
    """One tool invocation within a fixture, plus surrounding narration."""
    narration_before: str | None
    tool_name: str
    args: dict[str, Any]
    iteration: int


def _execute_steps(
    steps: list[_Step],
    initial_user_text: str,
    final_text: str,
) -> tuple[list[dict[str, Any]], list[ToolCall], int, int]:
    """Run all dispatcher calls and assemble a plausible message history.

    Returns (message_history, tool_call_log, approx_input_tokens,
    approx_output_tokens). Token counts are estimates derived from
    payload size to look plausible in the UI.
    """
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": initial_user_text},
    ]
    tool_call_log: list[ToolCall] = []
    input_tokens_est = 0
    output_tokens_est = 0

    # Group narration + tool calls into assistant turns. We model each
    # iteration as one assistant turn (text + 1-2 tool_use blocks)
    # followed by one user turn of tool_results. Real runs interleave
    # similarly.
    by_iter: dict[int, list[_Step]] = {}
    for s in steps:
        by_iter.setdefault(s.iteration, []).append(s)

    for it in sorted(by_iter):
        iter_steps = by_iter[it]
        # Assistant turn: concatenate any narration_before from these steps
        # into a single text block, then emit the tool_use blocks.
        assistant_blocks: list[dict[str, Any]] = []
        narr = " ".join(
            s.narration_before for s in iter_steps if s.narration_before
        ).strip()
        if narr:
            assistant_blocks.append({"type": "text", "text": narr})
            output_tokens_est += max(40, len(narr) // 4)

        # Tool uses.
        tool_use_ids: list[str] = []
        for i_in_iter, s in enumerate(iter_steps):
            tu_id = _toolu_id(it * 10 + i_in_iter)
            tool_use_ids.append(tu_id)
            assistant_blocks.append({
                "type": "tool_use",
                "id": tu_id,
                "name": s.tool_name,
                "input": s.args,
            })
            output_tokens_est += 40

        messages.append({"role": "assistant", "content": assistant_blocks})

        # User turn (tool_results).
        result_blocks: list[dict[str, Any]] = []
        for s, tu_id in zip(iter_steps, tool_use_ids):
            payload, call = dispatch(
                tool_name=s.tool_name,
                raw_args=s.args,
                iteration=it,
                tool_use_id=tu_id,
            )
            tool_call_log.append(call)
            content_str = json.dumps(payload, default=str)
            result_blocks.append({
                "type": "tool_result",
                "tool_use_id": tu_id,
                "content": content_str,
                "is_error": isinstance(payload, dict) and payload.get("is_error", False),
            })
            input_tokens_est += max(120, len(content_str) // 4)
        messages.append({"role": "user", "content": result_blocks})

    # Final assistant turn with the verdicts.
    messages.append({
        "role": "assistant",
        "content": [{"type": "text", "text": final_text}],
    })
    output_tokens_est += max(800, len(final_text) // 4)

    return messages, tool_call_log, input_tokens_est, output_tokens_est


def _build_run(
    *, defect_code: str, fund_id: str, as_of: date, share_class: str | None,
    suffix: str, steps: list[_Step], verdicts: list[Verdict],
    initial_user_text: str, final_text: str,
    notes: str = "",
) -> AgentRun:
    messages, tool_call_log, in_tokens, out_tokens = _execute_steps(
        steps, initial_user_text, final_text,
    )
    iterations = max((s.iteration for s in steps), default=0) + 1
    started = FIXTURE_CREATED + timedelta(seconds=hash(suffix) % 7200)
    finished = started + timedelta(milliseconds=11_000 + (hash(suffix) % 8_000))
    latency_ms = (finished - started).total_seconds() * 1000.0

    # Token usage: assume cache mostly read after first iteration.
    cache_creation = 12_500 if "first" in suffix else 0
    cache_read = 11_000 + (in_tokens // 2)
    token_usage = TokenUsage(
        input_tokens=in_tokens,
        output_tokens=out_tokens,
        cache_creation_input_tokens=cache_creation,
        cache_read_input_tokens=cache_read,
    )

    policy_actions = [apply_policy(v, fund_id) for v in verdicts]

    return AgentRun(
        run_id=_make_run_id(fund_id, as_of, suffix),
        fund_id=fund_id,
        as_of_date=as_of,
        share_class=share_class,
        model_version="claude-opus-4-7",
        prompt_version=prompt_version(),
        verdicts=verdicts,
        policy_actions=policy_actions,
        tool_call_log=tool_call_log,
        message_history=messages,
        token_usage=token_usage,
        total_latency_ms=latency_ms,
        iterations=iterations,
        converged=True,
        halted_reason=None,
        started_at=started,
        finished_at=finished,
    )


# ---------------------------------------------------------------------------
# Per-defect fixture builders
# ---------------------------------------------------------------------------
def _initial_user(fund_id: str, as_of: date, share_class: str | None) -> str:
    sc = f", share class {share_class}" if share_class else ""
    return (
        f"Evaluate the pre-close NAV pack for fund {fund_id}{sc} on "
        f"{as_of.isoformat()}. Work through the defect checklist. Use "
        "tools to gather evidence. Reconcile the day's NAV move in basis "
        "points against the drivers you identify. Produce one or more "
        "structured verdicts inside <verdicts>...</verdicts> at the end of "
        "your final response."
    )


def _verdicts_block(verdicts: list[Verdict]) -> str:
    items = [
        {
            "defect_type": v.defect_type,
            "severity": v.severity,
            "confidence": v.confidence,
            "evidence": [asdict(e) for e in v.evidence],
            "recommended_action": v.recommended_action,
            "reasoning": v.reasoning,
            "bps_impact": v.bps_impact,
        }
        for v in verdicts
    ]
    return json.dumps(items, indent=2, default=str)


def fixture_defect_1_merid_nesn() -> AgentRun:
    fund = "MERID"; as_of = date(2026, 1, 22)
    steps = [
        _Step("I'll start by orienting on the fund metadata and recent NAV trajectory.",
              "get_funds", {"fund_id": fund}, 0),
        _Step(None, "get_share_classes", {"fund_id": fund}, 0),
        _Step(None, "get_nav_history",
              {"fund_id": fund, "share_class": "I",
               "start_date": "2026-01-15", "end_date": "2026-01-22"}, 1),
        _Step("The day's NAV move is materially negative. Pull holdings and prices to attribute it.",
              "get_holdings", {"fund_id": fund, "as_of_date": "2026-01-22"}, 2),
        _Step(None, "get_holdings", {"fund_id": fund, "as_of_date": "2026-01-21"}, 2),
        _Step("One holding (Nestlé) shows up with a very large negative contribution. Confirm the price move.",
              "get_price_series",
              {"instrument_id": "EQ_EU_NESN",
               "start_date": "2026-01-21", "end_date": "2026-01-22"}, 3),
        _Step("Cross-check against the SECONDARY source to rule out a bad print.",
              "get_price_series",
              {"instrument_id": "EQ_EU_NESN",
               "start_date": "2026-01-21", "end_date": "2026-01-22",
               "source": "SECONDARY"}, 3),
        _Step("Both sources agree on a -22% move. Quantify the contribution.",
              "compute_nav_move_bps",
              {"nav_t": 95.40, "nav_t_minus_1": 96.96}, 4),
    ]
    verdicts = [
        Verdict(
            defect_type="single_stock_shock",
            severity="HIGH",
            confidence=0.93,
            evidence=[
                EvidenceItem(
                    description="Nestlé (EQ_EU_NESN) PRIMARY price moved -22.0% from 2026-01-21 to 2026-01-22; SECONDARY agrees within 8 bps.",
                    source_table="prices",
                    source_key={"instrument_id": "EQ_EU_NESN", "as_of_date": "2026-01-22"},
                    source_fields=["price"],
                    observed_value=70.57,
                    expected_value=90.47,
                ),
                EvidenceItem(
                    description="MERID held Nestlé at ~7% of fund AUM on 2026-01-21. The position contributes ~-154 bps to the -160 bps day move.",
                    source_table="holdings",
                    source_key={"fund_id": fund, "instrument_id": "EQ_EU_NESN", "as_of_date": "2026-01-21"},
                    source_fields=["mv_base"],
                    observed_value=5_127_414.76,
                    expected_value=None,
                ),
            ],
            recommended_action="URGENT_REVIEW",
            reasoning=(
                "MERID's NAV moved -160 bps day-over-day on 2026-01-22, "
                "exceeding the fund's 130 bps tolerance. Attribution decomposes "
                "almost entirely (-154 bps of -160) to a single name: Nestlé "
                "(EQ_EU_NESN), which dropped 22% on the day. The PRIMARY and "
                "SECONDARY pricing sources agree within 8 bps, so this is not a "
                "bad print -- it is a genuine market shock on a 7% position. "
                "Recommend URGENT_REVIEW so the analyst can confirm the news "
                "context (earnings miss, regulatory action, etc.) and corroborate "
                "before sign-off."
            ),
            bps_impact=-160.5,
        ),
    ]
    final = (
        "I have completed the checklist. Single-stock shock is the dominant driver "
        "and accounts for essentially all of the day's NAV move. No other category "
        "produced material evidence.\n\n"
        f"<verdicts>\n{_verdicts_block(verdicts)}\n</verdicts>"
    )
    return _build_run(
        defect_code="single_stock_shock", fund_id=fund, as_of=as_of,
        share_class=None, suffix="def001",
        steps=steps, verdicts=verdicts,
        initial_user_text=_initial_user(fund, as_of, None),
        final_text=final,
    )


def fixture_defect_2_pacif_fx() -> AgentRun:
    fund = "PACIF"; as_of = date(2026, 2, 25)
    steps = [
        _Step("Orient on the fund and check the day's NAV move.",
              "get_funds", {"fund_id": fund}, 0),
        _Step(None, "get_nav_history",
              {"fund_id": fund, "share_class": "I",
               "start_date": "2026-02-18", "end_date": "2026-02-25"}, 0),
        _Step("PACIF is a Japan-equity fund, USD base. NAV moved -233 bps. Most exposure is JPY -- check FX snaps.",
              "get_holdings", {"fund_id": fund, "as_of_date": "2026-02-25"}, 1),
        _Step("Pull all FX snaps for JPY on the as-of date to look for an intraday gap.",
              "get_fx_rates_all_snaps", {"ccy": "JPY", "as_of_date": "2026-02-25"}, 2),
        _Step("The LDN_4PM and NY_10AM JPY rates differ by ~2.5%. Verify which snap was used in the holdings revaluation.",
              "get_holdings", {"fund_id": fund, "as_of_date": "2026-02-25",
                              "instrument_id": "EQ_JP_TOYOTA"}, 3),
        _Step("Compute the implied gap if NY_10AM was used vs the policy LDN_4PM snap.",
              "compute_nav_move_bps", {"nav_t": 0.00646, "nav_t_minus_1": 0.00665}, 4),
    ]
    verdicts = [
        Verdict(
            defect_type="fx_cutoff_mismatch",
            severity="HIGH",
            confidence=0.91,
            evidence=[
                EvidenceItem(
                    description="JPY snaps on 2026-02-25 disagree by 2.50%: LDN_4PM=0.00665, NY_10AM=0.00649. PACIF's policy is to strike NAV using LDN_4PM.",
                    source_table="fx_rates",
                    source_key={"ccy": "JPY", "as_of_date": "2026-02-25"},
                    source_fields=["snap", "rate_to_usd"],
                    observed_value={"LDN_4PM": 0.00665, "NY_10AM": 0.00649},
                    expected_value="LDN_4PM applied per policy",
                ),
                EvidenceItem(
                    description="PACIF's holdings.fx_to_base for JPY positions on 2026-02-25 matches NY_10AM, not LDN_4PM. JPY weight is ~98% of fund.",
                    source_table="holdings",
                    source_key={"fund_id": fund, "as_of_date": "2026-02-25"},
                    source_fields=["fx_to_base", "ccy"],
                    observed_value=0.00649,
                    expected_value=0.00665,
                ),
            ],
            recommended_action="BLOCK_NAV",
            reasoning=(
                "PACIF NAV moved -233 bps on 2026-02-25. The fund holds ~98% JPY "
                "exposure and uses LDN_4PM FX snap per its valuation policy. On "
                "this day the LDN_4PM and NY_10AM JPY rates diverged by 2.5%, "
                "and the stored fx_to_base on PACIF's holdings matches NY_10AM "
                "rather than LDN_4PM. Revaluing under the policy snap recovers "
                "approximately 230 bps -- consistent with the unexplained "
                "portion of today's move. Recommend BLOCK_NAV until ops "
                "confirms the FX snap configuration and re-strikes."
            ),
            bps_impact=-233.3,
        ),
    ]
    final = (
        "FX cutoff mismatch is the cause. NAV should not be released until the "
        "snap is corrected.\n\n"
        f"<verdicts>\n{_verdicts_block(verdicts)}\n</verdicts>"
    )
    return _build_run(
        defect_code="fx_cutoff_mismatch", fund_id=fund, as_of=as_of,
        share_class=None, suffix="def002",
        steps=steps, verdicts=verdicts,
        initial_user_text=_initial_user(fund, as_of, None),
        final_text=final,
    )


def fixture_defect_3_helio_aapl() -> AgentRun:
    fund = "HELIO"; as_of = date(2026, 4, 2)
    steps = [
        _Step("Orient on the fund.",
              "get_funds", {"fund_id": fund}, 0),
        _Step(None, "get_nav_history",
              {"fund_id": fund, "share_class": "I",
               "start_date": "2026-03-26", "end_date": "2026-04-02"}, 0),
        _Step("HELIO NAV moved -117 bps. Check for corporate actions in the window.",
              "get_corporate_actions",
              {"start_date": "2026-04-01", "end_date": "2026-04-03",
               "ca_types": ["CASH_DIV", "SPECIAL_DIV"]}, 1),
        _Step("AAPL has a SPECIAL_DIV with ex_date 2026-04-02. Check if HELIO held it.",
              "get_holdings", {"fund_id": fund, "as_of_date": "2026-04-02",
                              "instrument_id": "EQ_US_AAPL"}, 2),
        _Step("HELIO holds ~12,300 AAPL shares. Verify the price drop on ex-date.",
              "get_price_around_date",
              {"instrument_id": "EQ_US_AAPL",
               "target_date": "2026-04-02", "lookback_days": 2,
               "lookahead_days": 0}, 3),
        _Step("Check whether the cash receipt was booked.",
              "get_dividend_receipts",
              {"fund_id": fund, "instrument_id": "EQ_US_AAPL",
               "start_date": "2026-04-02", "end_date": "2026-04-02"}, 4),
        _Step("Compute the implied dividend return and compare to the realized price drop.",
              "compute_implied_dividend_return",
              {"gross_amount": 27.78, "pre_ex_price": 185.20}, 5),
    ]
    verdicts = [
        Verdict(
            defect_type="missed_corp_action",
            severity="HIGH",
            confidence=0.94,
            evidence=[
                EvidenceItem(
                    description="AAPL SPECIAL_DIV (CA_DEFECT_3) ex_date 2026-04-02, gross 27.78 USD per share.",
                    source_table="corporate_actions",
                    source_key={"ca_id": "CA_DEFECT_3"},
                    source_fields=["ca_type", "ex_date", "gross_amount"],
                    observed_value=27.78,
                    expected_value=None,
                ),
                EvidenceItem(
                    description="HELIO held EQ_US_AAPL on ex-date with quantity 12,344 shares.",
                    source_table="holdings",
                    source_key={"fund_id": fund, "as_of_date": "2026-04-02", "instrument_id": "EQ_US_AAPL"},
                    source_fields=["quantity"],
                    observed_value=12_344.0,
                ),
                EvidenceItem(
                    description="AAPL price dropped 15.0% on ex-date (185.20 -> 157.42 PRIMARY); implied div return is -15.0%. Match within 0.1%.",
                    source_table="prices",
                    source_key={"instrument_id": "EQ_US_AAPL"},
                    source_fields=["price"],
                    observed_value=-0.150,
                    expected_value=-0.150,
                ),
                EvidenceItem(
                    description="No dividend_receipt row exists for (HELIO, EQ_US_AAPL, 2026-04-02). Expected gross receipt: 12,344 x 27.78 = 342,914 USD.",
                    source_table="dividend_receipts",
                    source_key={"fund_id": fund, "instrument_id": "EQ_US_AAPL", "as_of_date": "2026-04-02"},
                    source_fields=["receipt_id"],
                    observed_value=None,
                    expected_value=342_914.0,
                ),
            ],
            recommended_action="BLOCK_NAV",
            reasoning=(
                "HELIO failed to book a cash dividend receipt for AAPL on "
                "2026-04-02. The CA is real: AAPL price dropped 15.0% on "
                "ex-date and the implied drop from the gross amount is -15.0%, "
                "a near-exact match. HELIO held 12,344 AAPL shares on ex-date "
                "(~7% of fund AUM). With no receipt booked, NAV is short ~343k "
                "USD -- consistent with the fund's -117 bps move (expected "
                "~-105 bps from this miss alone, the remainder is normal "
                "intraday noise). Recommend BLOCK_NAV until ops books the "
                "receipt and re-strikes."
            ),
            bps_impact=-117.3,
        ),
    ]
    final = (
        "Missed corporate action confirmed. Smoking gun: CA exists in the market "
        "(price-drop matches implied), holding exists in fund, but no receipt was "
        "booked. NAV is short the dividend.\n\n"
        f"<verdicts>\n{_verdicts_block(verdicts)}\n</verdicts>"
    )
    return _build_run(
        defect_code="missed_corp_action", fund_id=fund, as_of=as_of,
        share_class=None, suffix="def003",
        steps=steps, verdicts=verdicts,
        initial_user_text=_initial_user(fund, as_of, None),
        final_text=final,
    )


def fixture_defect_4_nordic_lith() -> AgentRun:
    fund = "NORDIC"; as_of = date(2026, 2, 12)
    steps = [
        _Step("Orient on the fund.",
              "get_funds", {"fund_id": fund}, 0),
        _Step(None, "get_nav_history",
              {"fund_id": fund, "share_class": "I",
               "start_date": "2026-02-05", "end_date": "2026-02-12"}, 0),
        _Step("NAV moved -226 bps. Pull holdings and look at top contributors.",
              "get_holdings", {"fund_id": fund, "as_of_date": "2026-02-12"}, 1),
        _Step("Pull a 10-day price history for the largest names. Check Lithiumstad first.",
              "get_price_series",
              {"instrument_id": "EQ_NS_LITH",
               "start_date": "2026-02-02", "end_date": "2026-02-12"}, 2),
        _Step("PRIMARY price was unchanged for several days then dropped sharply on 2026-02-12. Check SECONDARY.",
              "get_price_series",
              {"instrument_id": "EQ_NS_LITH",
               "start_date": "2026-02-02", "end_date": "2026-02-12",
               "source": "SECONDARY"}, 3),
        _Step("Confirm the flat run with the dedicated detector.",
              "detect_flat_run_in_series",
              {"series": [
                  ["2026-02-06", 142.5],
                  ["2026-02-09", 142.5],
                  ["2026-02-10", 142.5],
                  ["2026-02-11", 142.5],
                  ["2026-02-12", 99.75],
              ], "min_length_days": 2}, 4),
    ]
    verdicts = [
        Verdict(
            defect_type="stale_price",
            severity="HIGH",
            confidence=0.89,
            evidence=[
                EvidenceItem(
                    description="EQ_NS_LITH PRIMARY price was identical (142.50) on 2026-02-09, 02-10, 02-11. Length-3 flat run.",
                    source_table="prices",
                    source_key={"instrument_id": "EQ_NS_LITH"},
                    source_fields=["price"],
                    observed_value=142.50,
                    expected_value="moving daily",
                ),
                EvidenceItem(
                    description="SECONDARY source moved during the same window (~143.20 -> 138.10), confirming PRIMARY was stale.",
                    source_table="prices",
                    source_key={"instrument_id": "EQ_NS_LITH", "source": "SECONDARY"},
                    source_fields=["price"],
                    observed_value=138.10,
                    expected_value=142.50,
                ),
                EvidenceItem(
                    description="On 2026-02-12 PRIMARY caught up: 142.50 -> 99.75 (-30%). NORDIC holds LITH at ~7% AUM, contributing ~-210 bps to the day's -226 bps move.",
                    source_table="holdings",
                    source_key={"fund_id": fund, "instrument_id": "EQ_NS_LITH"},
                    source_fields=["mv_base"],
                    observed_value=99.75,
                ),
            ],
            recommended_action="BLOCK_NAV",
            reasoning=(
                "EQ_NS_LITH is a Nordic small-cap held at ~7% of NORDIC. Its "
                "PRIMARY price feed reported the same value (142.50) for 3 "
                "consecutive business days -- 2026-02-09, 02-10, 02-11 -- "
                "while the SECONDARY source moved meaningfully during that "
                "window. On 2026-02-12 PRIMARY caught up with a -30% jump, "
                "creating an artificial discontinuity that drives ~-210 bps "
                "of the -226 bps fund-day move. The rest is normal noise. "
                "Recommend BLOCK_NAV until pricing is restated using the "
                "secondary feed for the affected days."
            ),
            bps_impact=-225.7,
        ),
    ]
    final = (
        "Stale-price catch-up. Cross-source disagreement plus a 3-day flat run "
        "is conclusive.\n\n"
        f"<verdicts>\n{_verdicts_block(verdicts)}\n</verdicts>"
    )
    return _build_run(
        defect_code="stale_price", fund_id=fund, as_of=as_of,
        share_class=None, suffix="def004",
        steps=steps, verdicts=verdicts,
        initial_user_text=_initial_user(fund, as_of, None),
        final_text=final,
    )


def fixture_defect_5_cobal_hwm() -> AgentRun:
    fund = "COBAL"; as_of = date(2026, 4, 15); sc = "I"
    steps = [
        _Step("Orient on the fund and the perf-fee terms.",
              "get_funds", {"fund_id": fund}, 0),
        _Step(None, "get_share_classes", {"fund_id": fund}, 0),
        _Step("Class I has a 20% perf fee with HWM. Pull NAV history for the full window to find the true HWM.",
              "get_nav_history",
              {"fund_id": fund, "share_class": sc,
               "start_date": "2026-01-05", "end_date": "2026-04-15"}, 1),
        _Step("Max prior NAV per share is ~102.5 (true HWM). Now look at fee_accruals on 2026-04-15.",
              "get_fee_accruals",
              {"fund_id": fund, "share_class": sc,
               "start_date": "2026-04-14", "end_date": "2026-04-15"}, 2),
        _Step("Stored hwm_nav_per_share is ~90 (well below 102.5). Compute what the perf fee should be.",
              "compute_perf_fee",
              {"nav_per_share": 102.79, "hwm_nav_per_share": 102.50,
               "hurdle_bps": 0, "perf_fee_bps": 2000, "period_days": 365}, 3),
        _Step("Now compute it with the (wrong) stale HWM.",
              "compute_perf_fee",
              {"nav_per_share": 102.79, "hwm_nav_per_share": 90.00,
               "hurdle_bps": 0, "perf_fee_bps": 2000, "period_days": 365}, 4),
    ]
    verdicts = [
        Verdict(
            defect_type="stale_hwm_perf_fee",
            severity="HIGH",
            confidence=0.92,
            evidence=[
                EvidenceItem(
                    description="Class I has perf_fee_bps=2000 with HWM=true. Initial NAV/share was 100.0.",
                    source_table="share_classes",
                    source_key={"fund_id": fund, "class_code": sc},
                    source_fields=["perf_fee_bps", "has_hwm"],
                    observed_value={"perf_fee_bps": 2000, "has_hwm": True},
                ),
                EvidenceItem(
                    description="Maximum prior NAV/share over the full window is 102.50. This is the true HWM under daily MTM.",
                    source_table="nav",
                    source_key={"fund_id": fund, "class_code": sc},
                    source_fields=["nav_per_share"],
                    observed_value=102.50,
                ),
                EvidenceItem(
                    description="On 2026-04-15 the stored hwm_nav_per_share is 90.00 -- materially below the true HWM. Perf fee is being accrued where none should be.",
                    source_table="fee_accruals",
                    source_key={"fund_id": fund, "class_code": sc, "as_of_date": "2026-04-15"},
                    source_fields=["hwm_nav_per_share", "perf_fee_balance"],
                    observed_value={"hwm_nav_per_share": 90.00, "perf_fee_balance": 25_580.0},
                    expected_value={"hwm_nav_per_share": 102.50, "perf_fee_balance": 580.0},
                ),
            ],
            recommended_action="BLOCK_NAV",
            reasoning=(
                "COBAL Class I shows a -201 bps NAV move on 2026-04-15. "
                "Perf-fee accrual is using a stale HWM (90.00) instead of the "
                "all-time-high prior NAV/share (102.50). This causes the fee "
                "engine to charge 20% of (102.79 - 90.00) per share rather than "
                "20% of (102.79 - 102.50). The over-accrual matches the "
                "unexplained portion of the day's move. Recommend BLOCK_NAV "
                "until the HWM reference is restated and the accrual recomputed."
            ),
            bps_impact=-201.2,
        ),
    ]
    final = (
        "Stale HWM in the perf-fee accrual. Reconciles to the unexplained portion "
        "of the day's NAV move.\n\n"
        f"<verdicts>\n{_verdicts_block(verdicts)}\n</verdicts>"
    )
    return _build_run(
        defect_code="stale_hwm_perf_fee", fund_id=fund, as_of=as_of,
        share_class=sc, suffix="def005",
        steps=steps, verdicts=verdicts,
        initial_user_text=_initial_user(fund, as_of, sc),
        final_text=final,
    )


def fixture_defect_6_helio_trade() -> AgentRun:
    fund = "HELIO"; as_of = date(2026, 2, 4)
    steps = [
        _Step("Orient on the fund.",
              "get_funds", {"fund_id": fund}, 0),
        _Step(None, "get_nav_history",
              {"fund_id": fund, "share_class": "I",
               "start_date": "2026-01-28", "end_date": "2026-02-04"}, 0),
        _Step("NAV move is sub-tolerance. Walk through the recon checks.",
              "get_trades",
              {"fund_id": fund,
               "start_date": "2026-02-04", "end_date": "2026-02-04"}, 1),
        _Step("One ASML trade is large. Check the position delta.",
              "get_holdings_history",
              {"fund_id": fund, "instrument_id": "EQ_EU_ASML",
               "start_date": "2026-02-03", "end_date": "2026-02-04"}, 2),
    ]
    verdicts = [
        Verdict(
            defect_type="trade_wrong_side",
            severity="MEDIUM",
            confidence=0.88,
            evidence=[
                EvidenceItem(
                    description="trade TR0000360 is recorded as SELL 432 of EQ_EU_ASML on 2026-02-04.",
                    source_table="trades",
                    source_key={"trade_id": "TR0000360"},
                    source_fields=["side", "quantity"],
                    observed_value={"side": "SELL", "quantity": 432},
                ),
                EvidenceItem(
                    description="HELIO's EQ_EU_ASML quantity went UP by 432 from 2026-02-03 to 2026-02-04. A SELL should have decreased it.",
                    source_table="holdings",
                    source_key={"fund_id": fund, "instrument_id": "EQ_EU_ASML"},
                    source_fields=["quantity"],
                    observed_value="+432",
                    expected_value="-432",
                ),
            ],
            recommended_action="REVIEW_QUEUE",
            reasoning=(
                "Trade ledger and position ledger disagree on EQ_EU_ASML for "
                "2026-02-04. trades.side=SELL 432, but holdings_history shows "
                "quantity went UP by 432 day-over-day. NAV impact is small "
                "(sub-tolerance), so this is not a strike-blocking issue, but "
                "it must be reconciled before next-day pricing. Either the "
                "trade was booked with the wrong side, or the position update "
                "applied the wrong sign."
            ),
            bps_impact=14.4,
        ),
    ]
    final = (
        "Trade-vs-position recon break. Sub-tolerance NAV impact, recommend the "
        "review queue for ops follow-up.\n\n"
        f"<verdicts>\n{_verdicts_block(verdicts)}\n</verdicts>"
    )
    return _build_run(
        defect_code="trade_wrong_side", fund_id=fund, as_of=as_of,
        share_class=None, suffix="def006",
        steps=steps, verdicts=verdicts,
        initial_user_text=_initial_user(fund, as_of, None),
        final_text=final,
    )


def fixture_defect_7_sterl_coupon() -> AgentRun:
    fund = "STERL"; as_of = date(2026, 3, 24)
    steps = [
        _Step("Orient on the fund.",
              "get_funds", {"fund_id": fund}, 0),
        _Step(None, "get_holdings", {"fund_id": fund, "as_of_date": "2026-03-24"}, 1),
        _Step("STERL is an IG bond fund. Check accrual time-series for the largest holdings.",
              "get_bond_accruals",
              {"instrument_id": "BND_GBP_BARC_2031",
               "start_date": "2026-03-15", "end_date": "2026-03-26"}, 2),
        _Step("Run the flat-run detector.",
              "detect_flat_run_in_series",
              {"series": [
                  ["2026-03-17", 1.5068],
                  ["2026-03-18", 1.5219],
                  ["2026-03-19", 1.5219],
                  ["2026-03-20", 1.5219],
                  ["2026-03-23", 1.5219],
                  ["2026-03-24", 1.5219],
                  ["2026-03-25", 1.5973],
              ], "min_length_days": 2}, 3),
        _Step("Compute the expected accrual over the 4 missed business days.",
              "compute_expected_coupon_accrual",
              {"face_value": 100.0, "coupon_rate": 0.055,
               "day_count_convention": "ACT/365", "days": 4}, 4),
    ]
    verdicts = [
        Verdict(
            defect_type="missed_coupon_accrual",
            severity="LOW",
            confidence=0.86,
            evidence=[
                EvidenceItem(
                    description="BARC 5.50% 2031 accrued_interest_pct held flat at 1.5219% from 2026-03-19 through 2026-03-24 (4 business days), then resumed normally on 2026-03-25.",
                    source_table="bond_accruals",
                    source_key={"instrument_id": "BND_GBP_BARC_2031"},
                    source_fields=["accrued_interest_pct"],
                    observed_value=1.5219,
                    expected_value="ticking up daily",
                ),
                EvidenceItem(
                    description="Expected 4-day accrual on 5.5% coupon is 0.0603% of face. STERL holds BARC at ~7% of fund.",
                    source_table=None,
                    source_key={},
                    source_fields=[],
                    observed_value=0.0,
                    expected_value=0.0603,
                ),
            ],
            recommended_action="LOG_ONLY",
            reasoning=(
                "Bond coupon accrual on BARC 5.50% 2031 stopped ticking for 4 "
                "business days. NAV impact is small (~4 bps -- well within "
                "STERL's tolerance). Sub-tolerance, no strike block, but the "
                "accrual engine should be investigated to confirm it has "
                "resumed cleanly across all bond holdings."
            ),
            bps_impact=4.2,
        ),
    ]
    final = (
        "Missed bond coupon accrual on BARC; small NAV impact, log for ops.\n\n"
        f"<verdicts>\n{_verdicts_block(verdicts)}\n</verdicts>"
    )
    return _build_run(
        defect_code="missed_coupon_accrual", fund_id=fund, as_of=as_of,
        share_class=None, suffix="def007",
        steps=steps, verdicts=verdicts,
        initial_user_text=_initial_user(fund, as_of, None),
        final_text=final,
    )


def fixture_defect_8_atlas_capstock() -> AgentRun:
    fund = "ATLAS"; as_of = date(2026, 3, 5); sc = "A"
    steps = [
        _Step("Orient and check both share classes for divergence.",
              "get_funds", {"fund_id": fund}, 0),
        _Step(None, "get_share_classes", {"fund_id": fund}, 0),
        _Step(None, "get_nav_history",
              {"fund_id": fund, "share_class": "A",
               "start_date": "2026-03-02", "end_date": "2026-03-05"}, 1),
        _Step(None, "get_nav_history",
              {"fund_id": fund, "share_class": "I",
               "start_date": "2026-03-02", "end_date": "2026-03-05"}, 1),
        _Step("Class A and Class I diverge by ~30 bps despite sharing the same portfolio. Check capstock.",
              "get_capstock",
              {"fund_id": fund, "share_class": sc,
               "start_date": "2026-03-05", "end_date": "2026-03-05"}, 2),
        _Step("CS_DEFECT_8 has order_received_ts 13:30 vs cutoff 12:00 -- post-cutoff but booked for today.",
              "get_fund_calendar", {"fund_id": fund, "share_class": sc}, 3),
    ]
    verdicts = [
        Verdict(
            defect_type="subscription_pre_cutoff",
            severity="MEDIUM",
            confidence=0.90,
            evidence=[
                EvidenceItem(
                    description="Capstock event CS_DEFECT_8: SUB of 50,000,000 USD; order_received_ts=2026-03-05T13:30, cutoff_ts=2026-03-05T12:00, booked_for_date=2026-03-05.",
                    source_table="capstock",
                    source_key={"capstock_id": "CS_DEFECT_8"},
                    source_fields=["order_received_ts", "cutoff_ts", "booked_for_date"],
                    observed_value={"order_received": "13:30", "cutoff": "12:00", "booked": "2026-03-05"},
                    expected_value={"booked_for_date": "2026-03-06"},
                ),
                EvidenceItem(
                    description="Class A NAV moved +52.6 bps; Class I (no capstock today) moved +22.3 bps. Same portfolio -- divergence ~30 bps consistent with intraday-gain dilution from a too-cheap subscription.",
                    source_table="nav",
                    source_key={"fund_id": fund, "as_of_date": "2026-03-05"},
                    source_fields=["nav_move_bps"],
                    observed_value={"A": 52.6, "I": 22.3},
                ),
            ],
            recommended_action="URGENT_REVIEW",
            reasoning=(
                "A 50M USD subscription into ATLAS Class A on 2026-03-05 was "
                "received at 13:30, after the 12:00 cutoff, but booked at "
                "today's NAV. With an intraday market gain, existing Class A "
                "holders were diluted by approximately 30 bps -- consistent "
                "with the unexplained delta between Class A and Class I NAV "
                "moves on the same day (same portfolio). Recommend "
                "URGENT_REVIEW: the dealing-cutoff rule is a UCITS investor-"
                "protection requirement and the policy override "
                "atlas_capstock_strict applies."
            ),
            bps_impact=52.6,
        ),
    ]
    final = (
        "Subscription stamped pre-cutoff but actually post-cutoff. Investor-"
        "protection issue.\n\n"
        f"<verdicts>\n{_verdicts_block(verdicts)}\n</verdicts>"
    )
    return _build_run(
        defect_code="subscription_pre_cutoff", fund_id=fund, as_of=as_of,
        share_class=sc, suffix="def008",
        steps=steps, verdicts=verdicts,
        initial_user_text=_initial_user(fund, as_of, sc),
        final_text=final,
    )


def fixture_defect_9_aurora_wht() -> AgentRun:
    fund = "AURORA"; as_of = date(2026, 3, 12)
    steps = [
        _Step("Orient and check the fund's domicile (relevant for treaty rates).",
              "get_funds", {"fund_id": fund}, 0),
        _Step(None, "get_fund_domicile", {"fund_id": fund}, 0),
        _Step("Pull dividend receipts for the day.",
              "get_dividend_receipts",
              {"fund_id": fund,
               "start_date": "2026-03-12", "end_date": "2026-03-12"}, 1),
        _Step("DR_DEFECT_9 has wht_rate_used=22% on a Samsung dividend. Look up the issuer's country.",
              "get_instruments", {"instrument_id": "EQ_EM_SAMSU"}, 2),
        _Step("Samsung is KR. Look up the LU-KR treaty rate.",
              "get_treaty_rate",
              {"domicile_country": "LU", "source_country": "KR"}, 3),
        _Step("Treaty rate is 15%; 22% was applied. Verify with implied rate calc.",
              "compute_implied_wht_rate",
              {"gross_amount": 168_643_167.31, "wht_amount": 37_101_496.81}, 4),
    ]
    verdicts = [
        Verdict(
            defect_type="wrong_wht",
            severity="LOW",
            confidence=0.96,
            evidence=[
                EvidenceItem(
                    description="dividend_receipts row DR_DEFECT_9: gross 168,643,167.31 KRW, wht_rate_used=22%, wht_amount=37,101,496.81 KRW.",
                    source_table="dividend_receipts",
                    source_key={"receipt_id": "DR_DEFECT_9"},
                    source_fields=["wht_rate_used", "gross_amount", "wht_amount"],
                    observed_value=0.22,
                ),
                EvidenceItem(
                    description="Issuer EQ_EM_SAMSU is KR. AURORA fund domicile is LU. wht_treaty(LU, KR) returns treaty=15%, statutory=22%.",
                    source_table="wht_treaty",
                    source_key={"domicile_country": "LU", "source_country": "KR"},
                    source_fields=["treaty_rate", "statutory_rate"],
                    observed_value=0.15,
                    expected_value=0.15,
                ),
                EvidenceItem(
                    description="Reclaimable amount: (0.22 - 0.15) x 168.6M KRW = 11.8M KRW (~9k USD at the day's FX). Cash short by this amount.",
                    source_table=None,
                    source_key={},
                    source_fields=[],
                    observed_value=11_805_022.0,
                ),
            ],
            recommended_action="LOG_ONLY",
            reasoning=(
                "Withholding tax on AURORA's Samsung dividend was applied at "
                "the Korean statutory rate (22%) rather than the LU-KR treaty "
                "rate (15%). The 7-percentage-point gap is reclaimable from "
                "Korean tax authorities. NAV impact today is sub-tolerance "
                "(<5 bps) -- this is a compliance / cash-recovery item rather "
                "than a strike-blocking defect. Log for the tax-reclaim "
                "workflow."
            ),
            bps_impact=-4.7,
        ),
    ]
    final = (
        "Wrong WHT on Samsung dividend. Reclaimable.\n\n"
        f"<verdicts>\n{_verdicts_block(verdicts)}\n</verdicts>"
    )
    return _build_run(
        defect_code="wrong_wht", fund_id=fund, as_of=as_of,
        share_class=None, suffix="def009",
        steps=steps, verdicts=verdicts,
        initial_user_text=_initial_user(fund, as_of, None),
        final_text=final,
    )


def fixture_defect_10_atlas_fee() -> AgentRun:
    fund = "ATLAS"; as_of = date(2026, 4, 23); sc = "I"
    steps = [
        _Step("Orient and pull both share classes' fee terms.",
              "get_share_classes", {"fund_id": fund}, 0),
        _Step("Pull NAV and fee accrual rows for both classes on the as-of date.",
              "get_nav_history",
              {"fund_id": fund, "share_class": "A",
               "start_date": "2026-04-22", "end_date": "2026-04-23"}, 1),
        _Step(None, "get_nav_history",
              {"fund_id": fund, "share_class": "I",
               "start_date": "2026-04-22", "end_date": "2026-04-23"}, 1),
        _Step(None, "get_fee_accruals",
              {"fund_id": fund, "share_class": "A",
               "start_date": "2026-04-23", "end_date": "2026-04-23"}, 2),
        _Step(None, "get_fee_accruals",
              {"fund_id": fund, "share_class": "I",
               "start_date": "2026-04-23", "end_date": "2026-04-23"}, 2),
    ]
    verdicts = [
        Verdict(
            defect_type="class_fee_misallocation",
            severity="LOW",
            confidence=0.83,
            evidence=[
                EvidenceItem(
                    description="Class I mgmt_fee_bps = 60 (institutional); expected daily fee = AUM * 60bps / 365.",
                    source_table="share_classes",
                    source_key={"fund_id": fund, "class_code": "I"},
                    source_fields=["mgmt_fee_bps"],
                    observed_value=60,
                ),
                EvidenceItem(
                    description="On 2026-04-23 Class I mgmt_fee_daily booked is 44,228 USD; expected based on Class I AUM is ~4,083 USD. Excess is ~10x.",
                    source_table="fee_accruals",
                    source_key={"fund_id": fund, "class_code": "I", "as_of_date": "2026-04-23"},
                    source_fields=["mgmt_fee_daily"],
                    observed_value=44_228.61,
                    expected_value=4_083.79,
                ),
                EvidenceItem(
                    description="Class A mgmt fee on the same day is 4,083 USD. The Class I overcharge matches Class A's daily fee being booked twice.",
                    source_table="fee_accruals",
                    source_key={"fund_id": fund, "class_code": "A", "as_of_date": "2026-04-23"},
                    source_fields=["mgmt_fee_daily"],
                    observed_value=4_083.79,
                ),
            ],
            recommended_action="LOG_ONLY",
            reasoning=(
                "ATLAS Class I shows an unexpectedly large management-fee "
                "accrual on 2026-04-23. Expected daily fee given Class I AUM "
                "and 60 bps annual is ~4,083 USD, but ~44,228 USD was booked "
                "-- almost exactly 10x. Class A's 150 bps fee on the same day "
                "is ~4,083 USD; the size of the Class I overcharge is "
                "consistent with Class A's fee being booked to Class I "
                "(possibly via a misconfigured allocation rule). NAV impact "
                "on Class I is sub-tolerance (~-9 bps), so log for follow-up "
                "rather than blocking the strike."
            ),
            bps_impact=-7.8,
        ),
    ]
    final = (
        "Class-level fee misallocation; Class I overcharged. Sub-tolerance, "
        "log for ops follow-up.\n\n"
        f"<verdicts>\n{_verdicts_block(verdicts)}\n</verdicts>"
    )
    return _build_run(
        defect_code="class_fee_misallocation", fund_id=fund, as_of=as_of,
        share_class=sc, suffix="def010",
        steps=steps, verdicts=verdicts,
        initial_user_text=_initial_user(fund, as_of, sc),
        final_text=final,
    )


def fixture_clean_run() -> AgentRun:
    fund = "STERL"; as_of = date(2026, 2, 19)
    steps = [
        _Step("Orient on the fund.",
              "get_funds", {"fund_id": fund}, 0),
        _Step(None, "get_nav_history",
              {"fund_id": fund, "share_class": "I",
               "start_date": "2026-02-12", "end_date": "2026-02-19"}, 0),
        _Step("NAV move is well within tolerance. Walk the checklist briefly.",
              "get_holdings", {"fund_id": fund, "as_of_date": "2026-02-19"}, 1),
        _Step(None, "get_corporate_actions",
              {"start_date": "2026-02-17", "end_date": "2026-02-20",
               "ca_types": ["CASH_DIV", "SPECIAL_DIV"]}, 1),
        _Step(None, "get_capstock",
              {"fund_id": fund, "share_class": "I",
               "start_date": "2026-02-19", "end_date": "2026-02-19"}, 2),
    ]
    verdicts = [
        Verdict(
            defect_type="no_defect",
            severity="NONE",
            confidence=0.91,
            evidence=[
                EvidenceItem(
                    description="NAV move on 2026-02-19 is +6.4 bps, comfortably within STERL's 125 bps tolerance.",
                    source_table="nav",
                    source_key={"fund_id": fund, "as_of_date": "2026-02-19"},
                    source_fields=["nav_move_bps"],
                    observed_value=6.4,
                ),
                EvidenceItem(
                    description="No corporate actions, no capstock activity, no flat runs in any held instrument's price or accrual series.",
                    source_table=None,
                    source_key={},
                    source_fields=[],
                    observed_value="clean across all 10 categories",
                ),
            ],
            recommended_action="AUTO_SIGN_OFF",
            reasoning=(
                "STERL on 2026-02-19 is a clean fund-day. NAV move is "
                "sub-tolerance. No corporate actions hit holdings on this "
                "date, no capstock events, no FX snap divergences, no flat "
                "runs in price or accrual series, no class-level fee "
                "anomalies. All 10 defect categories evaluated; none material."
            ),
            bps_impact=6.4,
        ),
    ]
    final = (
        "No defects detected. NAV move is normal sub-tolerance noise. "
        "Sign-off recommended.\n\n"
        f"<verdicts>\n{_verdicts_block(verdicts)}\n</verdicts>"
    )
    return _build_run(
        defect_code="no_defect", fund_id=fund, as_of=as_of,
        share_class="I", suffix="clean001",
        steps=steps, verdicts=verdicts,
        initial_user_text=_initial_user(fund, as_of, "I"),
        final_text=final,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
ALL_FIXTURE_BUILDERS = (
    fixture_defect_1_merid_nesn,
    fixture_defect_2_pacif_fx,
    fixture_defect_3_helio_aapl,
    fixture_defect_4_nordic_lith,
    fixture_defect_5_cobal_hwm,
    fixture_defect_6_helio_trade,
    fixture_defect_7_sterl_coupon,
    fixture_defect_8_atlas_capstock,
    fixture_defect_9_aurora_wht,
    fixture_defect_10_atlas_fee,
    fixture_clean_run,
)


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    manifest_entries: list[dict[str, Any]] = []
    for builder in ALL_FIXTURE_BUILDERS:
        run = builder()
        out_path = FIXTURES_DIR / f"{run.run_id}.json"
        out_path.write_text(
            json.dumps(to_json_dict(run), indent=2, default=str),
            encoding="utf-8",
        )
        primary_verdict = run.verdicts[0] if run.verdicts else None
        manifest_entries.append({
            "run_id": run.run_id,
            "fund_id": run.fund_id,
            "as_of_date": run.as_of_date.isoformat(),
            "share_class": run.share_class,
            "primary_defect_type": primary_verdict.defect_type if primary_verdict else None,
            "primary_severity": primary_verdict.severity if primary_verdict else None,
            "primary_confidence": primary_verdict.confidence if primary_verdict else None,
            "is_fixture": True,
            "file": out_path.name,
        })
        print(
            f"  wrote {out_path.name:75s} "
            f"({primary_verdict.defect_type if primary_verdict else '-'}, "
            f"{primary_verdict.severity if primary_verdict else '-'})"
        )

    MANIFEST_PATH.write_text(
        json.dumps({
            "generated_at": FIXTURE_CREATED.isoformat(),
            "count": len(manifest_entries),
            "fixtures": manifest_entries,
        }, indent=2),
        encoding="utf-8",
    )
    print(f"\nmanifest -> {MANIFEST_PATH}")
    print(f"total fixtures: {len(manifest_entries)}")


if __name__ == "__main__":
    main()
