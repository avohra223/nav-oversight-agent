# NAV Oversight Agent

An LLM agent that investigates daily NAV-tolerance breaks and other anomalies in a synthetic fund-administration warehouse, producing auditable verdicts. Built as a portfolio project showing how custodians and fund administrators (Citi, BNP Paribas Securities Services, SGSS, BBH, State Street, Northern Trust, Deutsche Bank) could automate the oversight workflow that today consumes 30–90 minutes of analyst time per break.

## The 10-defect test suite

Each defect lives on exactly one fund-day. The agent does not know which defect (if any) it is investigating. The full catalog is in [docs/defects.md](docs/defects.md).

| # | Defect | Fund / Instrument | Reasoning pattern |
|---|---|---|---|
| 1 | Single-stock shock | MERID / NESN.SW | Holdings × price attribution |
| 2 | FX cutoff snap mismatch | PACIF (JPY exposure) | Cross-snap FX reconciliation |
| 3 | Missed corporate action | HELIO / AAPL | CA vs cash receipt vs price drop |
| 4 | Stale price | NORDIC / LITH.ST | Time-series flat-run detection |
| 5 | Performance fee on stale HWM | COBAL Class I | High-water-mark rule logic |
| 6 | Trade booked on wrong side | HELIO / ASML.AS | Trade vs position-delta recon |
| 7 | Missed bond coupon accrual | STERL / BARC bond | Per-instrument time-series |
| 8 | Subscription stamped pre-cutoff | ATLAS Class A | Capstock timestamp + cross-class |
| 9 | Wrong WHT on foreign dividend | AURORA / Samsung | Treaty-rate cross-reference |
| 10 | Share-class fee misallocation | ATLAS Class I | Cross-class comparative reasoning |

## Architecture

```
DuckDB warehouse  ─►  tool layer  ─►  agent loop  ─►  verdict
  (read-only)         (facts only)    (Anthropic SDK)    │
                                                         ▼
                                                    policy layer
                                                         │
                                                         ▼
                                                    audit JSONL
                                                         │
                                                         ▼
                                                    Streamlit UI
```

- **Warehouse**: synthetic operational tables (positions, trades, prices, FX,
  CAs, capstock, dividend receipts, NAV, fees) generated from seed scripts.
- **Tool layer**: 25 typed Python tools split into reference / positions /
  market_data / income / nav_fees / computation. Tools return facts; never
  verdicts. See [tools/README.md](tools/README.md).
- **Agent loop** (Phase 3): Anthropic SDK tool-use loop. Composes tool
  outputs to investigate a fund-day and emit a Verdict.
- **Verdict**: structured object with `defect_type`, `severity`,
  `confidence`, `evidence`, `recommended_action`, `reasoning`. See
  [CLAUDE.md](CLAUDE.md#4-verdict-schema).
- **Policy layer** (Phase 4): maps verdicts to actions per fund per defect.
- **Audit log**: every tool call and verdict is JSONL-logged to `audit/`.
- **UI** (Phase 4): Streamlit — scenarios index → live agent reasoning →
  verdict + evidence panel.

## Status

- [x] **Phase 1** — DuckDB warehouse + 10 seeded defects + verification report.
- [x] **Phase 2** — Tool layer (25 tools, 6 modules) + audit logging + 86-test suite.
- [x] **Phase 3** — Agent loop with Anthropic SDK + policy layer + replay capability.
- [x] **Phase 4** — Streamlit UI with fixture-based audit replay (no API spend required).
- [ ] **Phase 5** — Eval harness measuring defect detection rate. *Next.*

## Running the demo

The UI ships with 11 pre-recorded `audit/agent_runs/fixture_*.json` files —
one per defect plus a clean run. The demo works fully offline; no API
key is needed to view, navigate, and inspect the agent's reasoning.

```bash
git clone https://github.com/avohra223/nav-oversight-agent.git
cd nav-oversight-agent

# Python 3.12+ recommended (developed on 3.14)
python -m venv .venv
. .venv/Scripts/activate           # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# Rebuild the warehouse (fixtures already in the repo, but the warehouse
# is gitignored and needs regenerating — deterministic from a fixed seed)
python scripts/generate_data.py

# Launch the UI
streamlit run ui/app.py
```

Open the local URL Streamlit prints. Walk through the five sidebar pages:

- **Dashboard** — multi-fund overview with severity, action, defect counts.
- **Defect Detail** — verdict cards, evidence chain, full message history.
- **Run Explorer** — historical runs with filters and CSV export.
- **Configuration** — edit `config/policies.yaml` from the form.
- **Run Live** — the only page that consumes API credits (gated).

### Run Live (consumes API credits)

This is the only path that bills your Anthropic API account. It is gated
behind both an environment variable check and an explicit
acknowledgement checkbox; the run button is disabled otherwise.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
streamlit run ui/app.py
# In the UI: navigate to Run Live, choose a fund/date/model, check the
# acknowledgement, click Run agent now.
```

To record a batch of real runs (e.g. for a portfolio demo) and have them
replace the bundled fixtures:

```bash
python scripts/record_demo_runs.py                # the 3 hero defects (3, 5, 9)
python scripts/record_demo_runs.py --all          # all 10 defects
python scripts/reset_to_fixtures.py --apply       # back to fixture-only
```

## Other entry points

```bash
# Print the 10-defect scenario index from the warehouse
python scripts/report_scenarios.py

# Run the Phase 2 tool test suite (no API needed)
python -m pytest tests/tools/

# Run the Phase 3 agent test suite (requires API key + budget)
python -m pytest tests/agent/

# Headless smoke test of every UI page
python scripts/smoke_test_ui.py
```

The warehouse file `data/nav.duckdb` is gitignored — it is always
regenerated from scripts. Anyone cloning the repo gets the same warehouse
because `RANDOM_SEED` in [src/nav_oversight/config.py](src/nav_oversight/config.py)
is fixed.

## Limitations

- **Synthetic data only.** No real fund, custodian, or NAV data is used.
  Tickers are real but prices/holdings/CAs are randomly generated. Realistic
  distributions, not realistic levels.
- **Fixed defect taxonomy.** The agent is evaluated against the 10 defect
  categories above. Novel defect types outside this taxonomy are
  out-of-scope; the agent will return `defect_type='no_defect'` or the
  closest category with low confidence.
- **Open-ended fund paradigm only.** The warehouse models open-ended mutual
  funds / SICAVs / hedge funds (daily-priced, daily-dealing). Closed-end
  funds, ETFs, and private-market structures are out of scope.
- **Bounded schema.** v0 omits FC cash ledgers, swing pricing, expense caps,
  dividend equalisation, T+2 settlement, and most regulatory reporting. The
  defects are designed to be findable within the schema as-is.
- **No production hardening.** No auth, no rate limiting, no error budgets,
  no failover. This is a portfolio demo.

## Repository structure

```
nav-oversight-agent/
├── CLAUDE.md                    durable architectural spec
├── README.md                    you are here
├── requirements.txt
├── docs/
│   ├── defects.md               full 10-defect catalog
│   └── architecture.md          agent design notes
├── src/nav_oversight/           Phase 1: warehouse generators
│   ├── config.py                fund universe, defect schedule, vol params
│   ├── schema.py                DuckDB DDL
│   ├── defects.py               pre-walk + post-walk defect injectors
│   ├── build.py                 orchestrator
│   └── generators/              per-table generators (FX, prices, walk-forward, …)
├── agent/                       Phase 3: agent loop (Anthropic SDK)
│   ├── core.py                  run_agent + tool-use cycle
│   ├── dispatcher.py            LLM tool_use -> Phase 2 tools
│   ├── policies.py              verdict -> action resolution
│   ├── replay.py                tolerance-based diff
│   ├── schemas.py               AgentRun / Verdict / EvidenceItem
│   └── prompts/                 system prompt + defect checklist
├── ui/                          Phase 4: Streamlit UI (fixture-driven)
│   ├── app.py                   entrypoint
│   ├── styling.py               enterprise theme
│   ├── data_loaders.py          load AgentRun JSONs
│   ├── components/              verdict_card, evidence_chain, etc.
│   └── pages/                   dashboard, defect detail, explorer, config, run-live
├── config/policies.yaml         policy rules with per-fund overrides
├── tools/                       Phase 2: tool layer (facts not verdicts)
│   ├── README.md                tool inventory and design
│   ├── reference.py             funds, classes, instruments, treaty, calendar
│   ├── positions.py             holdings, trades, cash, capstock
│   ├── market_data.py           prices, FX, bond accruals
│   ├── income.py                corporate actions, dividend receipts
│   ├── nav_fees.py              NAV history, fee accruals
│   ├── computation.py           pure functions (no DB)
│   ├── _types.py                shared dataclasses
│   ├── _db.py                   read-only DuckDB connection
│   └── _audit.py                @audit_tool decorator + JSONL writer
├── tests/tools/                 86 tests: per-tool unit, hygiene linter, recon
├── scripts/
│   ├── generate_data.py         rebuild data/nav.duckdb from seed
│   └── report_scenarios.py      print the 10-defect scenario index
├── data/                        warehouse (.duckdb files, gitignored)
└── audit/                       runtime tool-call log (.jsonl, gitignored)
```
