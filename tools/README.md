# Tool Layer

This directory contains the **tool layer** that the NAV-oversight agent will call in Phase 3. Phase 2's deliverable is just the tools and their tests -- no agent loop, no prompts, no UI.

## Design principle: facts, not verdicts

A tool returns raw or computed data. A tool **must not** make a determination about whether a defect exists, whether a value is "correct," or whether a fund-day is "in breach." The agent's job is to compose multiple tool outputs and reason about them.

What this looks like in practice:

| Allowed | Forbidden |
|---|---|
| `get_dividend_receipts(...)` | `check_wht_compliance(...)` |
| `get_treaty_rate(...)` | `validate_dividend_receipts(...)` |
| `compute_implied_wht_rate(gross, wht)` | `is_wht_correct(receipt)` |
| `detect_flat_run_in_series(series, min_length)` | `find_stale_prices(fund)` |

The function `detect_flat_run_in_series` is named with the `detect_` prefix because the user requested that name explicitly. It is structurally a fact-returner -- it reports *where* the series is flat, never *whether* that's wrong. The hygiene linter has it on its allow-list.

## Forbidden columns

The warehouse has a few columns that exist only for ground-truth / verification. Tools MUST NOT project them:

- `corporate_actions.applied_flag` -- would leak defect 3.
- `nav.is_break` -- would leak which fund-days the warehouse pre-flagged.
- `trades.booking_note` -- would leak defect 6.
- `defect_catalog.*` -- the entire ground-truth table.

The linter at `tests/tools/test_tool_hygiene.py` scans every `.py` in this directory and fails the test suite if any forbidden column appears in a SQL string.

## Forbidden tool name prefixes

- `detect_` (one explicit exception: `detect_flat_run_in_series`)
- `check_`
- `validate_`
- `find_`
- `is_`

Any tool starting with these prefixes embeds a verdict. Decompose into `get_*` and `compute_*` primitives.

## Tool inventory

### A. Reference and metadata (`reference.py`)

| Tool | Returns |
|---|---|
| `get_funds(fund_id=None)` | `list[Fund]` |
| `get_share_classes(fund_id)` | `list[ShareClass]` |
| `get_fund_domicile(fund_id)` | `str \| None` |
| `get_instruments(instrument_id=None, ticker=None, ccy=None, country=None)` | `list[Instrument]` |
| `get_treaty_rate(domicile_country, source_country)` | `TreatyRate \| None` |
| `get_fund_calendar(fund_id, share_class)` | `FundCalendar` |

### B. Positions and transactions (`positions.py`)

| Tool | Returns |
|---|---|
| `get_holdings(fund_id, as_of_date, instrument_id=None)` | `list[Holding]` |
| `get_holdings_history(fund_id, instrument_id, start_date, end_date)` | `pd.DataFrame` |
| `get_trades(fund_id, date_range, instrument_id=None)` | `list[Trade]` |
| `get_cash(fund_id, as_of_date, ccy=None)` | `list[CashBalance]` |
| `get_capstock(fund_id, share_class, date_range)` | `list[CapstockEvent]` |

### C. Market data (`market_data.py`)

| Tool | Returns |
|---|---|
| `get_price_series(instrument_id, start_date, end_date, source='PRIMARY')` | `pd.DataFrame` |
| `get_price_around_date(instrument_id, target_date, lookback_days=5, lookahead_days=1, source='PRIMARY')` | `pd.DataFrame` |
| `get_fx_rate(ccy, as_of_date, snap='LDN_4PM')` | `FxRate \| None` |
| `get_fx_rates_all_snaps(ccy, as_of_date)` | `list[FxRate]` |
| `get_bond_accruals(instrument_id, start_date, end_date)` | `pd.DataFrame` |

### D. Income and corporate actions (`income.py`)

| Tool | Returns |
|---|---|
| `get_corporate_actions(instrument_id=None, date_range=None, ca_types=None)` | `list[CorporateAction]` |
| `get_dividend_receipts(fund_id=None, instrument_id=None, date_range=None)` | `list[DividendReceipt]` |

### E. NAV and fees (`nav_fees.py`)

| Tool | Returns |
|---|---|
| `get_nav_history(fund_id, share_class, start_date, end_date)` | `pd.DataFrame` |
| `get_fee_accruals(fund_id, share_class, date_range)` | `list[FeeAccrual]` |

### F. Pure computation (`computation.py`)

| Tool | Returns |
|---|---|
| `compute_implied_dividend_return(gross_amount, pre_ex_price)` | `float` |
| `compute_implied_wht_rate(gross_amount, wht_amount)` | `float` |
| `compute_expected_coupon_accrual(face_value, coupon_rate, day_count_convention, days)` | `float` |
| `compute_perf_fee(nav_per_share, hwm_nav_per_share, hurdle_bps, perf_fee_bps, period_days)` | `float` |
| `compute_attribution(holdings_t, holdings_t_minus_1, prices_t, prices_t_minus_1)` | `list[AttributionLine]` |
| `detect_flat_run_in_series(series, min_length_days, tolerance=1e-9)` | `list[FlatRunSegment]` |
| `compute_nav_move_bps(nav_t, nav_t_minus_1)` | `float` |

## Audit log

Every tool call writes one JSONL line to `audit/tool_calls.jsonl`:

```json
{"ts":"2026-05-03T12:34:56.789Z","tool":"reference.get_funds",
 "input":{"args":[],"kwargs":{"fund_id":"AURORA"}},
 "output":{"type":"list","row_count":1,"element_type":"Fund"},
 "latency_ms":3.142,"error":null,"pid":1234}
```

The summarizer is in `_audit.py`. Output payloads are summarized (row count + columns), not embedded in full -- the agent's reasoning chain is in the model context, not the audit log. Tests assert each tool emits exactly one line per call.

## Connection management

`_db.py` holds a single read-only DuckDB connection for the process. Tools share it; results are not cached. Tests can override the warehouse path via `set_db_path(...)` before any tool is called.

## Composition example

This is what the agent will do for defect 3 (missed CA on HELIO 2026-04-02), expressed as straight Python over the tool layer:

```python
from datetime import date
from tools.income import get_corporate_actions, get_dividend_receipts
from tools.market_data import get_price_around_date
from tools.positions import get_holdings
from tools.computation import compute_implied_dividend_return

# 1. Find any CAs in the window
cas = get_corporate_actions(
    date_range=(date(2026,4,1), date(2026,4,3)),
    ca_types=['CASH_DIV','SPECIAL_DIV'])

for ca in cas:
    # 2. Was the fund holding it on ex_date?
    held = get_holdings('HELIO', ca.ex_date, ca.instrument_id)
    if not held or held[0].quantity == 0:
        continue
    # 3. Did a receipt land on the pay date?
    receipts = get_dividend_receipts(
        fund_id='HELIO', instrument_id=ca.instrument_id,
        date_range=(ca.pay_date, ca.pay_date))
    # 4. Did the price drop by ~ the dividend on ex_date?
    px = get_price_around_date(ca.instrument_id, ca.ex_date,
                               lookback_days=2, lookahead_days=0)
    pre = px[px['as_of_date'] < ca.ex_date].iloc[-1]['price']
    on_ex = px[px['as_of_date'] == ca.ex_date].iloc[0]['price']
    realized = (on_ex - pre) / pre
    implied = compute_implied_dividend_return(ca.gross_amount, pre)
    if not receipts and realized < implied * 0.5:
        # The agent draws the conclusion. The tools never did.
        print(f"missed CA {ca.ca_id} on HELIO/{ca.instrument_id}")
```
