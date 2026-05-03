# CLAUDE.md — Architectural Principles

This file is the durable spec for the project. Read it before making changes.

## 1. Project purpose

**NAV Defect Detection Agent** for fund administration. Custodian and fund-admin
banks (Citi, BNP Paribas Securities Services, Société Générale Securities
Services, BBH, State Street, Northern Trust, Deutsche Bank) compute net asset
values (NAVs) every day for thousands of funds. Each NAV requires oversight:
an analyst investigates day-over-day moves, fee accruals, capstock activity,
corporate actions, and FX revaluations to confirm the NAV is correct or
escalate a defect.

This project automates that oversight workflow with a single LLM agent that
queries a fund-administration warehouse via a typed tool layer, finds defects,
and produces an auditable verdict per investigation.

## 2. The 10-defect test suite framing

There is **one agent, not ten**. The ten defects are *test cases* that
exercise different reasoning patterns the agent must master. The agent never
knows in advance which defect category it is investigating.

| # | Defect | Reasoning pattern |
|---|--------|---|
| 1 | Single-stock shock | Holdings × price attribution math |
| 2 | FX cutoff snap mismatch | Cross-snap FX reconciliation |
| 3 | Missed corporate action | CA presence vs. cash receipt vs. price drop |
| 4 | Stale price / vendor feed dropped | Time-series flat-run detection |
| 5 | Performance fee on stale HWM | High-water-mark rule logic |
| 6 | Trade booked on wrong side | Trade vs. position-delta reconciliation |
| 7 | Missed bond coupon accrual | Per-instrument time-series check |
| 8 | Subscription stamped pre-cutoff | Capstock timestamp + cross-class divergence |
| 9 | Wrong WHT on foreign dividend | Treaty-rate cross-reference |
| 10 | Share-class fee misallocation | Cross-class comparative reasoning |

See [docs/defects.md](docs/defects.md) for the full catalog.

## 3. Tool design principle: facts, not verdicts

A tool returns raw or computed data. A tool **must not** make a determination
about whether a defect exists, whether a value is "correct," or whether a
fund-day is "in breach." The agent's job is to compose multiple tool outputs
and reason over them.

| Allowed | Forbidden |
|---|---|
| `get_dividend_receipts(...)` | `check_wht_compliance(...)` |
| `get_treaty_rate(...)` | `validate_dividend_receipts(...)` |
| `compute_implied_wht_rate(g, w)` | `is_wht_correct(receipt)` |

### 3.1 Forbidden tool name prefixes

- `detect_`
- `check_`
- `validate_`
- `find_`
- `is_`

**Documented exception:** `detect_flat_run_in_series` is permitted because it
returns a fact (*where* the series is flat) and never a verdict (*whether*
that's wrong). The hygiene linter has it on its allow-list. No other
exception will be granted; if you find yourself wanting one, the tool is
embedding a verdict — decompose it.

### 3.2 Forbidden columns and tables

The warehouse contains ground-truth columns and tables used only by seed
generators and verification reports. Tools must never project these:

**Forbidden columns** (do not appear in any `SELECT` clause inside `tools/`):
- `corporate_actions.applied_flag`
- `nav.is_break`
- `trades.booking_note`

**Forbidden tables** (do not appear anywhere in `tools/`):
- `defect_catalog`
- `ground_truth`

Enforcement: [tests/tools/test_tool_hygiene.py](tests/tools/test_tool_hygiene.py)
scans every `.py` in `tools/` and fails the suite if any forbidden token
appears.

## 4. Verdict schema

Every agent investigation produces exactly one Verdict object:

```python
@dataclass
class Verdict:
    investigation_id: str
    fund_id: str
    as_of_date: date
    share_class: str | None
    defect_type: str          # 'single_stock_shock' | 'fx_cutoff_mismatch' | ... | 'no_defect'
    severity: str             # 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
    confidence: float         # [0.0, 1.0]
    evidence: list[Evidence]  # pointers into the warehouse (table, key, fields)
    recommended_action: str   # 'SIGN_OFF' | 'ESCALATE' | 'RESTATE' | 'ADJUST'
    reasoning: str            # free-text, model-generated
    bps_impact: float | None  # signed NAV impact in basis points, when computable
    tool_calls: list[str]     # references into audit/tool_calls.jsonl
```

Where `Evidence` is:

```python
@dataclass
class Evidence:
    description: str          # one line of plain English
    source_table: str         # e.g. 'dividend_receipts'
    source_key: dict          # {'receipt_id': 'DR_DEFECT_9'}
    source_fields: list[str]  # ['wht_rate_used', 'gross_amount']
    observed_value: object    # actual value from the warehouse
    expected_value: object | None  # what the agent thought it should be, if applicable
```

Verdicts are persisted as JSON. A verdict whose `defect_type == 'no_defect'`
is still a valid output (the agent investigated and concluded nothing was
wrong). The agent must never refuse to produce a verdict.

## 5. Policy layer

The verdict captures **what is true**. The policy layer captures **what to
do about it**. They are separated so policy is changeable without retraining
or re-prompting the agent.

```python
@dataclass
class PolicyRule:
    fund_id: str | None       # None matches all funds
    defect_type: str | None   # None matches all defects
    min_severity: str
    action: str               # 'AUTO_SIGN_OFF' | 'NOTIFY_ANALYST' | 'BLOCK_NAV_RELEASE' | ...
    notification_channel: str | None   # 'slack:#oversight', 'email:ops-lead@…'
```

Policy resolution: take the agent's verdict, walk policy rules in
specificity order (fund+defect → fund-only → defect-only → default), apply
the first match. Per-fund overrides allow a hedge fund (COBAL) to auto-sign
LOW-severity stale-HWM cases that would block a UCITS fund.

Policy rules live in `policy/rules.yaml` (Phase 4). The agent does NOT see
or invoke policy; it only emits verdicts.

## 6. Audit and replay

Every tool call writes one JSONL line to `audit/tool_calls.jsonl`:

```json
{"ts":"2026-05-03T03:15:29.459+00:00","tool":"reference.get_funds",
 "input":{"args":[],"kwargs":{}},
 "output":{"type":"list","row_count":8,"element_type":"Fund"},
 "latency_ms":47.074,"error":null,"pid":41492}
```

Requirements:

- **Determinism within a fixed warehouse.** Tools return the same data for
  the same inputs against the same `data/nav.duckdb`. The agent's reasoning
  is non-deterministic (model sampling), but the data layer is not.
- **Full reproducibility.** Given an investigation_id, the audit log lists
  every tool call (with inputs) and the verdict. Re-running the same calls
  against the same warehouse must produce the same tool outputs.
- **No tool may cache across calls.** Caching breaks replay and obscures the
  actual data dependencies.
- **No mutating SQL.** Tools open a read-only DuckDB handle.
- **Audit failures must not break tool calls.** A failure to write to the
  audit log is logged but swallowed; the tool returns its result.

## 7. Stack

| Layer | Technology |
|---|---|
| Warehouse | DuckDB (single-file, read-only from tools) |
| Synthetic data generators | Python + numpy + pandas |
| Tool layer | Pure Python with strict type hints; no ORMs |
| Agent loop | Anthropic Python SDK with tool use + prompt caching |
| UI | **Streamlit** (NOT React/FastAPI). Single-process, simple to demo. |
| Tests | pytest |

The choice of Streamlit is deliberate: this is a portfolio / demo project,
not a production system. Streamlit gives a credible interactive UI in a few
hundred lines without backend/frontend split.

## 8. Phase status

- [x] **Phase 1 — Data layer.** DuckDB warehouse with 8 funds, ~106
  instruments, 84 business days of synthetic positions / trades / capstock /
  prices / FX / corporate actions. 10 defects seeded on specific fund-days.
  See `src/nav_oversight/`, `scripts/generate_data.py`,
  `scripts/report_scenarios.py`.

- [x] **Phase 2 — Tool layer.** 25 tools across 6 modules under `tools/`.
  All facts-not-verdicts, all type-hinted, all audit-logged. 86-test suite
  covering happy / empty / invalid / edge for every tool, plus a hygiene
  linter and two end-to-end recon tests (defects 3 and 9) that prove the
  tool layer is sufficient to find defects without leaking ground truth.

- [x] **Phase 3 — Agent loop.** Anthropic SDK tool-use loop with prompt
  caching against `claude-opus-4-7`. 26 tools registered with the agent
  (Phase 2 tools, with LLM-friendly arg adaptation). System prompt + 10
  defect category checklist, both versioned via SHA-256 hash recorded
  with each run. Hybrid reasoning: fixed checklist guarantees coverage,
  open reasoning within each category. Batch execution; streaming is
  Phase 4. Replay capability with tolerance-based diff (verdicts and
  severities must match exactly, confidence within ±0.20, tool overlap
  Jaccard ≥ 0.50). Policy layer applied after verdicts.

- [ ] **Phase 4 — UI.** Streamlit app: scenarios index → click a fund-day →
  agent streams its reasoning → final verdict + evidence + policy action.

- [ ] **Phase 5 — Hardening.** Eval suite that runs the agent against all
  10 defects + the baseline-noise breaks; measures defect detection rate,
  false-positive rate, mean confidence on correct verdicts.

### Phase 3 specifics

- **Model.** `claude-opus-4-7`. The defect checklist is large; Opus's
  reasoning is the right tool for the job. Cost ~$3-5 per investigation
  with caching.
- **Prompt versioning.** `agent/versioning.py:prompt_version()` returns
  the first 12 hex chars of `sha256(system_prompt + defect_checklist)`.
  Recorded in every `AgentRun` and used for filtering / regression
  analysis when prompts change.
- **Replay tolerance.** Same verdict types and severities (exact match),
  confidence within ±0.20, tool-name Jaccard ≥ 0.50. Reasoning text may
  vary freely. Captured in `agent/replay.py:ReplayDiff`.
- **False-positive policy.** On clean fund-days the agent is allowed to
  emit LOW-severity verdicts (sub-tolerance noise). HIGH or CRITICAL on
  a clean day fails the no-FP test in `tests/agent/`. The intent: better
  to log a curiosity than to scream.
- **Token budget.** Default 200k tokens per run; if exceeded, the run
  halts with `halted_reason="token_budget"` and a `agent_did_not_converge`
  verdict is emitted. Loop also halts on `max_iterations=50`.
- **API safety.** All Anthropic calls go through `agent/api_wrapper.py`,
  which retries on 429/5xx with exponential backoff and surfaces token
  usage to the loop for budget enforcement. No tool ever invokes the
  Anthropic API directly.

## 9. Reference

- [README.md](README.md) — project overview, repo layout, run instructions.
- [docs/defects.md](docs/defects.md) — full catalog of the 10 seeded defects.
- [docs/architecture.md](docs/architecture.md) — agent design (single-agent
  multi-defect, four pillars, data flow, hygiene linter).
- [tools/README.md](tools/README.md) — tool inventory and design notes.
