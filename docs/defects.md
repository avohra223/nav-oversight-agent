# Defect Catalog

The 10 defects below are seeded by [src/nav_oversight/defects.py](../src/nav_oversight/defects.py) on specific fund-days. Five produce direct NAV-tolerance breaks (the agent's primary investigation feed); five are sub-tolerance and require the agent to compose specialized anomaly checks. The split mirrors how real fund-administration oversight works — tolerance breaks are one feed among many.

| # | Code | Fund | As-of | Class | Category | Reasoning pattern | Smoking-gun field (ground truth, not visible to tools) |
|---|------|------|-------|-------|----------|-------------------|--------------------------------|
| 1 | `single_stock_shock`       | MERID  | 2026-01-22 | — | Market   | Holdings × price attribution | n/a (price drop is genuine) |
| 2 | `fx_cutoff_mismatch`       | PACIF  | 2026-02-25 | — | FX       | Cross-snap FX reconciliation | `fx_rates(JPY, NY_10AM)` vs `fx_rates(JPY, LDN_4PM)` gap |
| 3 | `missed_corp_action`       | HELIO  | 2026-04-02 | — | CA       | CA presence + price drop − cash receipt | `corporate_actions.applied_flag` (FORBIDDEN to tools) |
| 4 | `stale_price`              | NORDIC | 2026-02-12 | — | Pricing  | Time-series flat-run detection | `prices.price` flat for 3 consecutive days |
| 5 | `stale_hwm_perf_fee`       | COBAL  | 2026-04-15 | I | Fees     | High-water-mark math | `fee_accruals.hwm_nav_per_share` is below true HWM |
| 6 | `trade_wrong_side`         | HELIO  | 2026-02-04 | — | Recon    | Trade.side vs holdings delta | `trades.booking_note` (FORBIDDEN to tools) |
| 7 | `missed_coupon_accrual`    | STERL  | 2026-03-24 | — | Income   | Per-instrument time-series check | `bond_accruals.accrued_interest_pct` flat for 4 days |
| 8 | `subscription_pre_cutoff`  | ATLAS  | 2026-03-05 | A | Capstock | Timestamp + cross-class divergence | `capstock.order_received_ts > cutoff_ts` |
| 9 | `wrong_wht`                | AURORA | 2026-03-12 | — | Tax      | Treaty-rate cross-reference | `dividend_receipts.wht_rate_used` ≠ `wht_treaty.treaty_rate` |
| 10| `class_fee_misallocation`  | ATLAS  | 2026-04-23 | I | Fees     | Cross-class fee comparison | `fee_accruals.mgmt_fee_daily` ≠ AUM × rate / 365 |

## Detection split

**Produces a tolerance break** (`nav.is_break = TRUE` against fund's tolerance_bps):
1, 2, 3, 4, 5

**Sub-tolerance** (NAV move on the defect day is too small to clear tolerance, so the agent must run a specialized anomaly check to find it):
6, 7, 8, 9, 10

This split is intentional. Real ops teams run multiple monitoring streams in parallel: tolerance breaks, recon mismatches, compliance gates, cross-share-class divergence, treaty-rate audits. The agent exercises all of these.

## Reasoning patterns covered

| Pattern | Defect # |
|---|---|
| Holdings × price contribution math | 1, 6 |
| Time-series anomaly on a single instrument | 4, 7 |
| Cross-source / cross-snap reconciliation | 2 |
| Cross-table consistency check (CA ↔ price ↔ cash) | 3 |
| Domain-rule arithmetic (HWM, perf fee, fee schedule) | 5, 10 |
| Reference-data lookup against an applied value | 9 |
| Timestamp / cutoff fairness | 8 |
| Cross-share-class divergence | 8, 10 |

## Defect details

### 1. Single-stock shock (MERID, NESN.SW, 2026-01-22)
The price of Nestlé drops 30% from 2026-01-21 close to 2026-01-22 close (and the drop propagates forward). Nestlé is ~7% of MERID. The fund's NAV moves ~−160 bps, exceeding MERID's tolerance of 130 bps. Not really an "error" — a real-world idiosyncratic shock. The agent must isolate it from broad-market beta to deliver the right attribution.

Detection signal: holdings-attribution math identifies a single instrument as the dominant negative contributor.

### 2. FX cutoff snap mismatch (PACIF, 2026-02-25)
PACIF's policy is to strike NAV using LDN_4PM FX rates. On 2026-02-25 the operations team accidentally used NY_10AM rates for the JPY exposure. The two snaps diverge by 2.5% on this day. PACIF holds ~98% JPY, so the NAV is mismarked by ~−233 bps.

Detection signal: `fx_rates` table exposes both snaps. The agent recomputes fund MV under each snap and matches the gap to the observed NAV move.

### 3. Missed corporate action (HELIO, AAPL, 2026-04-02)
A 15% special dividend on AAPL is announced and goes ex-date on 2026-04-02. The price drops by 15% (the market correctly applies the ex-date adjustment). HELIO holds AAPL at ~7%. Operations failed to book the cash receipt. NAV is short by ~7% × 15% ≈ −105 bps.

Detection signal: a CA exists, the price-drop confirms the CA actually happened in the market, but `dividend_receipts` has no row for HELIO/AAPL on the pay date. The agent's recon test [tests/tools/test_recon_defect_3.py](../tests/tools/test_recon_defect_3.py) reproduces this exact reasoning.

### 4. Stale price (NORDIC, LITH.ST, 2026-02-09 → 2026-02-12)
The vendor feed for LITH.ST drops out for 3 consecutive business days (2026-02-09, 02-10, 02-11), reporting the same price each day. On 2026-02-12 the price catches up to a level 30% below the stale value. NORDIC holds LITH at ~7%, NAV moves ~−226 bps.

Detection signal: `tools.computation.detect_flat_run_in_series` reveals 3 consecutive days of identical PRIMARY price, contradicted by the SECONDARY source which moved during the same period.

### 5. Performance fee on stale HWM (COBAL Class I, 2026-04-15)
COBAL Class I's HWM ought to be its inception NAV (100). On 2026-04-15 the fee engine references a stale HWM of 90 (a previous low). The 20% perf fee is therefore charged on `(NAV − 90) × shares × 0.20` rather than `(NAV − 100) × shares × 0.20`, over-accruing by ~−201 bps.

Detection signal: `fee_accruals.hwm_nav_per_share` on the defect day reads 90 — which is below the all-time-high prior NAV in `nav.nav_per_share`. Inconsistency.

### 6. Trade booked on wrong side (HELIO, ASML.AS, 2026-02-04)
A trade for ASML on 2026-02-04 was a BUY in reality. Operations recorded it as a SELL. Holdings actually moved in the BUY direction (because the original walk used the correct side). After the post-walk flip, `trades.side` says SELL but `holdings.quantity` went up. NAV is internally consistent — no tolerance break. But the trade ledger and position ledger disagree.

Detection signal: compare `trades` for `(fund, trade_date)` to `holdings_history` quantity delta. The signed delta does not match the trade.

### 7. Missed bond coupon accrual (STERL, BARC bond, 2026-03-19 → 2026-03-24)
The accrual engine fails to tick `bond_accruals.accrued_interest_pct` for the BARC 5.5% 2031 bond for 4 consecutive business days. NAV is understated by a tiny amount (~5 bps) because accrued interest carries into MV.

Detection signal: `detect_flat_run_in_series` over `bond_accruals` finds the 4-day flat run; `compute_expected_coupon_accrual` shows what should have been booked.

### 8. Subscription stamped pre-cutoff (ATLAS Class A, 2026-03-05)
A $50M subscription arrives at 13:30 (after the 12:00 cutoff). Operations stamps the order as 11:45 and books it for today's NAV instead of tomorrow's. The market has gained intraday, so existing Class A holders are diluted by the new investor getting in cheap. Class I (no capstock event today) moved as expected; Class A's move is materially smaller. Sub-tolerance per Class A's threshold but visible as cross-class divergence.

Detection signal: `capstock.order_received_ts > cutoff_ts AND booked_for_date = as_of_date`. Confirmed by Class A vs Class I NAV move divergence on the same day.

### 9. Wrong WHT on Samsung dividend (AURORA, 2026-03-12)
AURORA (Luxembourg domicile) receives a Samsung Electronics dividend on 2026-03-12. The LU–KR treaty rate is 15%; Korean statutory is 22%. The custodian applied 22% (paperwork wasn't on file). 7% of the gross dividend is reclaimable but currently sitting with Korean tax authorities.

Detection signal: `dividend_receipts.wht_rate_used` (0.22) > `wht_treaty.treaty_rate(LU, KR)` (0.15) by more than a basis-point tolerance. The agent's recon test [tests/tools/test_recon_defect_9.py](../tests/tools/test_recon_defect_9.py) reproduces this.

### 10. Share-class fee misallocation (ATLAS Class I, 2026-04-23)
The fee engine charges Class A's mgmt fee accrual to Class I in addition to its own. Class I's NAV is depressed by the unwarranted extra fee, ~−8 bps. Sub-tolerance, but visible by comparing Class I's NAV move and fee accrual against expectation derived from `share_classes.mgmt_fee_bps × class AUM × 1/365`.

Detection signal: `fee_accruals.mgmt_fee_daily` for ATLAS/I is materially larger than the expected daily fee given `share_classes.mgmt_fee_bps × nav_base / 365`. Cross-checked against Class A's NAV move (which moved as expected for both classes' shared portfolio).
