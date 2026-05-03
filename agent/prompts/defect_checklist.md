# Defect checklist

For each fund-day you investigate, walk through the 10 categories below.
For each category, decide whether it applies, gather evidence, and reach
a conclusion. Always emit a verdict for any category where you found
something material.

The checklist is the same for every fund-day. The agent does not know in
advance which (if any) defect is present.

---

## 1. Single-stock shock

**What it is.** One holding moves materially (e.g. > 8% absolute return
on the day) and drives a meaningful share of the fund-level NAV move.
This is often a real market event, not an error — but it must be
*identified and quantified* so the analyst can confirm the move was
genuinely market-driven and not a bad print.

**Reasoning pattern.**
1. Pull holdings on the as-of date and the prior business day.
2. Pull PRIMARY prices for both days for each held instrument.
3. Run `compute_attribution` to get per-instrument contribution in local
   ccy. Convert to base ccy and to bps of fund AUM.
4. Identify any instrument whose contribution is more than ~30% of the
   total NAV move and whose price return is > 5% in absolute value.
5. Cross-check: does the SECONDARY price source agree on the move? A
   bad print would show as a PRIMARY/SECONDARY disagreement.

**Suggested tools.** `get_holdings`, `get_price_series`,
`compute_attribution`, `compute_nav_move_bps`.

**What lowers confidence.** Multiple instruments contribute roughly
equally (no single dominant driver); SECONDARY price agrees with PRIMARY
(rules out bad print but the shock is real); the move is consistent with
the broader sector or region.

---

## 2. FX cutoff snap mismatch

**What it is.** The fund's stated valuation policy uses a specific FX
snap (e.g. LDN_4PM). On a given day, operations may have used a
different snap (e.g. NY_10AM) for FX revaluation. Intraday FX moves on
the day are then incorrectly reflected in NAV.

**Reasoning pattern.**
1. Identify the fund's non-base-currency exposures (look at holdings ccy
   distribution).
2. For each major foreign ccy, pull `get_fx_rates_all_snaps` on the
   as-of date.
3. Compute the snap-to-snap gap. If meaningful (> 50 bps for a major
   ccy), revalue the affected positions under each snap and compare to
   the observed mv_base in `get_holdings`.
4. The smoking gun: the stored `holdings.fx_to_base` matches a
   non-policy snap, and the resulting bps gap matches the unexplained
   portion of the day's NAV move.

**Suggested tools.** `get_holdings`, `get_fx_rates_all_snaps`,
`get_nav_history`, `compute_nav_move_bps`.

**What lowers confidence.** The snap-to-snap gap is small (< 25 bps).
The bps gap doesn't fully reconcile. The fund holds a single FC and the
move could equally be a single-stock effect.

---

## 3. Missed corporate action

**What it is.** A cash dividend or special dividend was announced and
went ex-date for an instrument the fund holds. The price dropped by the
dividend amount on ex-date (the market always applies the adjustment),
but no cash receipt was booked for the fund. NAV is short the dividend.

**Reasoning pattern.**
1. Get all `CASH_DIV` / `SPECIAL_DIV` corporate actions in a window
   around the as-of date (covering ex-dates that would pay near today).
2. For each, check if the fund held the underlying on ex-date
   (`get_holdings`).
3. For each held position, compare:
   - The price-drop on ex-date (`get_price_around_date` for ex_date − 1
     and ex_date) against `compute_implied_dividend_return(gross_amount,
     pre_ex_price)`. The realized drop should be ≈ the implied drop. If
     so, the CA actually happened in the market.
   - Whether a `dividend_receipt` row exists for `(fund_id,
     instrument_id, pay_date)`.
4. If the CA happened (price corroborates) AND no receipt exists →
   missed CA.

**Suggested tools.** `get_corporate_actions`, `get_holdings`,
`get_price_around_date`, `get_dividend_receipts`,
`compute_implied_dividend_return`.

**What lowers confidence.** The price drop differs significantly from
the implied return — the CA may have been cancelled or revised, in
which case the absent receipt is correct. No price drop at all on
ex-date is also suspicious; check both PRIMARY and SECONDARY sources.

---

## 4. Stale price

**What it is.** The market data vendor's PRIMARY feed for one
instrument silently held a value flat for several days while the true
price moved. When the feed comes back, NAV takes a discontinuity.

**Reasoning pattern.**
1. Pull `get_holdings` to enumerate the fund's positions.
2. For each holding (or for the largest contributors to today's NAV
   move), pull `get_price_series` PRIMARY for the last ~10 business days.
3. Run `detect_flat_run_in_series` with `min_length_days=2`. Multi-day
   flat runs on actively-traded instruments are suspicious.
4. Cross-check against SECONDARY: does the secondary source show
   movement during the same window? If so, PRIMARY is stale.
5. If the as-of date is itself the catch-up day (price moves a lot
   after a flat run), the bps impact is the catch-up amount.

**Suggested tools.** `get_holdings`, `get_price_series` (both sources),
`detect_flat_run_in_series`.

**What lowers confidence.** The flat run is short (1-2 days). The
instrument is illiquid (e.g. a small-cap bond) where flat days are
normal. SECONDARY also shows no movement.

---

## 5. Performance fee on stale HWM

**What it is.** A fund with a high-water-mark perf fee (check
`share_classes.has_hwm`) is using a stale HWM lower than the true
all-time-high NAV per share. Result: perf fee is accrued on what should
be sub-HWM territory, depressing NAV.

**Reasoning pattern.**
1. Confirm the share class has a HWM (`get_share_classes`).
2. Pull `get_nav_history` for a long window ending on the as-of date.
3. Compute the maximum prior `nav_per_share` — that is the *true* HWM
   (under daily MTM). Compare against `fee_accruals.hwm_nav_per_share`
   on the as-of date.
4. If the stored HWM is materially below the true HWM AND there is a
   nonzero `perf_fee_balance`, recompute the expected fee with
   `compute_perf_fee` using the true HWM and compare to the stored
   `perf_fee_balance`.

**Suggested tools.** `get_share_classes`, `get_nav_history`,
`get_fee_accruals`, `compute_perf_fee`.

**What lowers confidence.** The stored HWM is not actually below the
true HWM. The class has no perf fee. The class is a Founder/F class
where HWM resets on a different schedule.

---

## 6. Trade booked on wrong side

**What it is.** A trade is recorded with the wrong side (BUY vs SELL).
The position ledger reflects the *correct* side, so trades and holdings
don't agree on what happened. Sub-tolerance NAV impact but a recon
break.

**Reasoning pattern.**
1. Pull `get_trades` for the fund on the as-of date.
2. For each trade, pull `get_holdings_history` for the same instrument
   on (trade_date − 1) and trade_date. Compute the quantity delta.
3. The delta should match the trade: BUY ⇒ +quantity, SELL ⇒
   −quantity. Allow for other contemporaneous trades on the same
   instrument by summing all trades' signed quantities first.
4. If the sum of signed trade quantities ≠ holdings delta, you have a
   recon break. The sign of the mismatch tells you which side was
   flipped.

**Suggested tools.** `get_trades`, `get_holdings_history`.

**What lowers confidence.** The mismatch is small (< 1% of trade size,
plausibly a corporate action or rounding). Multiple trades on the same
day make it hard to attribute to any single one.

---

## 7. Missed bond coupon accrual

**What it is.** A bond's accrued interest series stopped ticking up for
several business days. NAV is understated by the missed accrual.

**Reasoning pattern.**
1. From `get_holdings`, identify bond holdings (instrument type =
   `BOND`).
2. For each, pull `get_bond_accruals` for ~10 business days ending on
   the as-of date.
3. Run `detect_flat_run_in_series` with `min_length_days=2`. Bonds
   should accrue every business day (skipping coupon-pay-date resets,
   which are rare in any 10-day window).
4. For any flat run, compare the missed days against
   `compute_expected_coupon_accrual(face_value, coupon_rate, "ACT/365",
   missed_days)`.

**Suggested tools.** `get_holdings` (filter for type=BOND),
`get_instruments` (for face_value, coupon_rate),
`get_bond_accruals`, `detect_flat_run_in_series`,
`compute_expected_coupon_accrual`.

**What lowers confidence.** The flat run coincides with a coupon-pay
date (resets are legitimate). The bond is matured / called — accrual
stops correctly.

---

## 8. Subscription stamped pre-cutoff

**What it is.** An investor subscription arrived after the dealing
cutoff but was stamped pre-cutoff and booked at today's NAV instead of
tomorrow's. If the market moved intraday, existing investors are
diluted.

**Reasoning pattern.**
1. Pull `get_capstock` for the share class on the as-of date.
2. For each event, compare `order_received_ts` to `cutoff_ts`. If
   `order_received_ts > cutoff_ts` AND `booked_for_date == as_of_date`,
   that is a fairness violation.
3. Cross-check by comparing today's NAV move on the affected class
   versus another class of the same fund (which would not have been
   diluted). Material divergence corroborates.

**Suggested tools.** `get_capstock`, `get_fund_calendar`,
`get_nav_history` (for both classes).

**What lowers confidence.** The order is a redemption, not a
subscription (different fairness implications). Only one share class
exists, so cross-class corroboration isn't possible.

---

## 9. Wrong WHT on foreign dividend

**What it is.** A dividend received from a foreign issuer was withheld
at the source country's statutory rate instead of the treaty rate
applicable to the fund's domicile. Reclaimable amount = (used − treaty)
× gross.

**Reasoning pattern.**
1. Pull `get_dividend_receipts` for the fund in a window.
2. For each receipt, look up the issuer's country
   (`get_instruments(instrument_id).country`) and the fund's domicile
   (`get_fund_domicile`).
3. Look up the (domicile, source) pair in `get_treaty_rate`.
4. Compare `wht_rate_used` to `treaty_rate`. A material gap (> 1 percentage
   point) means too much was withheld.

**Suggested tools.** `get_dividend_receipts`, `get_instruments`,
`get_fund_domicile`, `get_treaty_rate`.

**What lowers confidence.** No treaty exists for the pair (gap matches
statutory by design). The receipt is from a domestic issuer where WHT
expectation is 0.

---

## 10. Share-class fee misallocation

**What it is.** Two share classes of the same fund have different fee
schedules (e.g. Class A 150 bps, Class I 60 bps). The fee engine
charges Class A's daily mgmt fee to Class I, depressing Class I's NAV.

**Reasoning pattern.**
1. List share classes from `get_share_classes`.
2. For each class, pull `get_fee_accruals` and `get_nav_history` for
   the as-of date.
3. Compute expected daily mgmt fee per class as `class_NAV_base ×
   (mgmt_fee_bps / 10000) / 365`. Compare to
   `fee_accruals.mgmt_fee_daily`. Material gap → misallocation.
4. Corroborate by comparing the day's nav_move_bps for both classes.
   Same portfolio — they should move similarly minus the fee
   differential. A larger-than-expected divergence supports the
   finding.

**Suggested tools.** `get_share_classes`, `get_fee_accruals`,
`get_nav_history`.

**What lowers confidence.** Only one share class exists. The classes
have different inception dates / structural fee schedules. Capstock
events on the as-of date can also produce class-level NAV divergence
that is unrelated to fees (cross-check capstock first).

---

## End-of-investigation checklist

- [ ] Did I orient (funds, share_classes, domicile, nav_history)?
- [ ] Did I compute the day's NAV move in bps and compare to tolerance?
- [ ] Did I walk all 10 categories at least briefly?
- [ ] For each defect I'm flagging, did I corroborate with at least 2
      independent signals?
- [ ] For each defect I'm flagging, did I attempt a bps reconciliation?
- [ ] Did I emit a single `<verdicts>...</verdicts>` JSON block at the
      end?
