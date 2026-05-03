# Architecture Notes

## 1. The single-agent multi-defect framing

There is **one agent**, not ten. The 10 defect categories from
[docs/defects.md](defects.md) are *test cases* that exercise different
reasoning patterns the agent must master. The agent is given a fund-day to
investigate, not a defect category to confirm.

This matters because the alternative — ten specialist agents, one per defect
type — would collapse into the agent layer the same kind of "verdict
embedding" we forbid in the tool layer. A specialist `wht_compliance_agent`
would be primed to find WHT defects, biasing its reasoning. A general agent
must construct its own hypotheses from raw facts.

Operationally, this also matches the real world: an oversight analyst at
SGSS doesn't know on Monday morning whether today's NAV break is from a
single-stock shock, a CA mistake, or a stale price. They follow a generic
investigation playbook and converge on the cause through evidence.

## 2. The four pillars

A trustworthy agent in this domain stands on four pillars. Phase 3 will
implement #1 and #3; #2 is Phase 2 (done); #4 spans Phase 2 (audit log) and
Phase 3 (verdict persistence + replay).

### 2.1 Trigger

What invokes the agent. Sources include:
- A NAV-tolerance break row (`nav.is_break = TRUE` in seed data; in
  production, computed by the policy layer from `nav.nav_move_bps` against
  fund tolerance).
- An anomaly-detector hit (e.g. cross-source price disagreement, missed
  expected dividend receipt, capstock timestamp anomaly, cross-class
  divergence).
- An ad-hoc analyst query: "investigate ATLAS A 2026-03-05 for me."

The agent does not select its own triggers. The trigger system enumerates
fund-days to investigate and feeds them in. This separation keeps the agent
from gaming its own evaluation.

### 2.2 Tools

Already built. See [tools/README.md](../tools/README.md) and
[CLAUDE.md §3](../CLAUDE.md#3-tool-design-principle-facts-not-verdicts).

### 2.3 Confidence

The agent must emit a calibrated confidence in [0, 1] alongside every
verdict. Calibration matters because:
- The policy layer routes by `severity × confidence`. A LOW-confidence HIGH
  severity verdict goes to a human; a HIGH-confidence LOW severity goes to
  an auto-action queue.
- The eval suite (Phase 5) checks that confidence correlates with
  correctness. An agent that always returns 0.99 confidence is uninformative
  even if its accuracy is high.

Implementation: the agent reasons about evidence completeness ("did I find
the smoking gun? did the bps reconcile? is there a competing hypothesis?")
and emits a confidence reflecting that. We will not use logprobs as a
proxy.

### 2.4 Audit

Every tool call is JSONL-logged ([CLAUDE.md §6](../CLAUDE.md#6-audit-and-replay)).
Every verdict is persisted with references to the tool calls that supported
it. Given an `investigation_id`, we can:

1. Replay the tool calls (deterministic against the warehouse).
2. Reproduce the agent's evidence list (deterministic).
3. Re-run the model on the same conversation (non-deterministic but tracked
   against a model+temperature+seed signature).

Audit is the foundation of *defensibility*. A regulator or fund board asking
"why did your system sign off on this NAV?" needs more than a chat
transcript.

## 3. Data flow

```
                ┌──────────────────────────┐
                │  warehouse: nav.duckdb   │
                │  (read-only, single file)│
                └─────────────┬────────────┘
                              │
                              │ parameterized SELECT
                              ▼
                ┌──────────────────────────┐
                │  tool layer              │
                │  - facts only            │
                │  - typed dataclasses     │
                │  - one connection        │
                │  - audit-decorated       │
                └─────────────┬────────────┘
                              │
                              │ tool-use cycle
                              ▼
                ┌──────────────────────────┐
                │  agent loop              │
                │  - Anthropic SDK         │
                │  - prompt-cached system  │
                │    prompt + tool schemas │
                │  - per-investigation     │
                │    fresh conversation    │
                └─────────────┬────────────┘
                              │
                              │ structured output
                              ▼
                ┌──────────────────────────┐
                │  Verdict                 │
                │  defect_type, severity,  │
                │  confidence, evidence,   │
                │  reasoning, bps_impact   │
                └──────┬───────────────┬───┘
                       │               │
                       │               │
              ┌────────▼─────────┐    │
              │  policy layer    │    │
              │  per-fund rules  │    │
              └────────┬─────────┘    │
                       │              │
              ┌────────▼─────────┐   ┌▼─────────────────┐
              │  action queue    │   │  audit log       │
              │  (sign-off /     │   │  - tool_calls    │
              │   escalate /     │   │  - verdicts      │
              │   restate)       │   │  - replay-able   │
              └────────┬─────────┘   └──────────────────┘
                       │
                       ▼
              ┌──────────────────┐
              │  Streamlit UI    │
              │  scenarios → live│
              │  reasoning →     │
              │  verdict + plan  │
              └──────────────────┘
```

## 4. Why deterministic tools matter

The agent's reasoning is non-deterministic — the model samples tokens, and
even with `temperature=0` outputs can drift across model versions. We accept
this for the *interpretation* layer. We do not accept it for the *data*
layer.

If `get_holdings('PACIF', date(2026,2,25))` returned different rows on
different calls, audit replay would be impossible. Worse, the agent's
reasoning could be self-contradictory within a single investigation
("earlier I found 25 holdings, now I find 27"). So:

- Tools never cache.
- Tools never order non-deterministically (every SQL has an `ORDER BY`).
- Tools never use random sampling, time-of-day, or any environment-derived
  inputs.
- Tools open a read-only DuckDB handle. No mutating SQL anywhere in
  `tools/`.

This guarantees that for a fixed `data/nav.duckdb`, the function
`tool(args) → output` is mathematically a function. Replay therefore works.

## 5. The hygiene linter

[tests/tools/test_tool_hygiene.py](../tests/tools/test_tool_hygiene.py)
runs four checks against every `.py` in `tools/`:

1. **No forbidden columns projected.** Scans string literals containing
   `SELECT` for `applied_flag`, `is_break`, `booking_note`. These columns
   exist in the warehouse only as ground truth — selecting them would leak
   the answer to the agent.

2. **No forbidden tables referenced.** Scans the entire source for
   `defect_catalog` and `ground_truth`. The defect catalog is the
   verification key for the eval harness; tools must never see it.

3. **No verdict-prefixed tool names.** Scans top-level function names for
   `detect_`, `check_`, `validate_`, `find_`, `is_`. One explicit allow-list
   entry: `detect_flat_run_in_series`. Any other tool with these prefixes
   must be decomposed into `get_*` or `compute_*` primitives.

4. **No string-interpolated SQL.** Scans for f-strings and `.format()` calls
   on SQL-shaped strings. Allows the safe pattern of f-stringing the
   placeholder count for `IN (?, ?, ?)` clauses (the values are still
   parameter-bound).

All four checks must pass for the test suite to pass. Adding a new tool
requires it to clear these gates first.

## 6. What the agent does NOT do

The boundaries are as important as the capabilities.

- **The agent does not write to the warehouse.** All tool connections are
  read-only.
- **The agent does not select its own triggers.** Trigger curation is
  upstream.
- **The agent does not apply policy.** It emits a verdict; the policy layer
  decides what to do with it.
- **The agent does not store its own state across investigations.** Each
  investigation gets a fresh conversation. Cross-investigation memory is in
  the audit log, not the prompt.
- **The agent does not modify its own tools.** Tool schemas are part of the
  cached system prompt; mutating them invalidates the cache and breaks
  reproducibility.

## 7. Non-goals

- Real-time trading signals, alpha generation, portfolio construction.
- Sub-second latency. Investigations target ~5–30 seconds end-to-end.
- Multi-agent coordination. One agent per investigation.
- LLM fine-tuning. We rely on prompting and tool design, not weights.
