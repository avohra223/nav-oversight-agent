"""Defect injectors.

Two phases:
  PRE-walk:  mutate input tables (prices, FX, CAs, bond_accruals).
             walk_forward then re-derives holdings/NAV consistently with the
             "broken" world.
  POST-walk: mutate derived tables directly (holdings, fee_accruals, capstock,
             dividend_receipts, nav). Used for behavior overrides where the
             walk does the right thing under normal rules but the defect is
             precisely a deviation from those rules.

Each defect is small and self-contained. The defect catalog rows
(in `defect_catalog`) are updated with the realized bps impact for verification.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

import duckdb

from .config import (
    DEFECT_SCHEDULE, FUNDS, FX_VS_USD_INITIAL, DefectSpec,
)
from .generators.reference import (
    ALL_INSTRUMENTS, FUND_DOMICILES, get_wht_rates,
)


_INSTRUMENT_BY_ID = {i.instrument_id: i for i in ALL_INSTRUMENTS}
_FUND_BY_ID = {f.fund_id: f for f in FUNDS}


def _prior_business_day(d: date) -> date:
    """Naive: skip weekends only."""
    cur = d - timedelta(days=1)
    while cur.weekday() >= 5:
        cur -= timedelta(days=1)
    return cur


# ----------------------------------------------------------------------------
# PRE-walk mutations
# ----------------------------------------------------------------------------
def apply_pre_walk_defects(con: duckdb.DuckDBPyConnection) -> None:
    """Mutate input tables for defects that walk_forward can re-derive."""
    for spec in DEFECT_SCHEDULE:
        if spec.code == "single_stock_shock":
            _defect_1_single_stock_shock(con, spec)
        elif spec.code == "missed_corp_action":
            _defect_3_missed_corp_action(con, spec)
        elif spec.code == "stale_price":
            _defect_4_stale_price(con, spec)
        elif spec.code == "missed_coupon_accrual":
            _defect_7_missed_coupon_accrual(con, spec)


def _defect_1_single_stock_shock(con, spec: DefectSpec) -> None:
    instr_id = spec.params["instrument_id"]
    shock = spec.params["shock_pct"]
    d = spec.as_of

    # Apply a one-day shock that PROPAGATES forward (multiply all prices from
    # `d` onward by (1+shock)). Without propagation the next day's NAV bounces
    # back when the factor model continues from the unshocked price level.
    factor_today_row = con.execute(
        "SELECT price FROM prices WHERE instrument_id=? AND as_of_date=? AND source='PRIMARY'",
        [instr_id, d],
    ).fetchone()
    if factor_today_row is None:
        return
    prior = _prior_business_day(d)
    prior_row = con.execute(
        "SELECT price FROM prices WHERE instrument_id=? AND as_of_date=? AND source='PRIMARY'",
        [instr_id, prior],
    ).fetchone()
    if prior_row is None:
        return
    target_today = float(prior_row[0]) * (1.0 + shock)
    scale = target_today / float(factor_today_row[0])
    con.execute(
        "UPDATE prices SET price = price * ? "
        "WHERE instrument_id=? AND as_of_date >= ? AND source='PRIMARY'",
        [scale, instr_id, d],
    )
    con.execute(
        "UPDATE prices SET price = price * ? "
        "WHERE instrument_id=? AND as_of_date >= ? AND source='SECONDARY'",
        [scale, instr_id, d],
    )


def _defect_3_missed_corp_action(con, spec: DefectSpec) -> None:
    """Insert a SPECIAL_DIV with applied_flag=FALSE and apply the post-ex
    price drop on AAPL from the as_of date onward."""
    instr_id = spec.params["instrument_id"]
    div_pct = spec.params["div_pct"]
    d = spec.as_of
    prior = _prior_business_day(d)
    prior_price = con.execute(
        "SELECT price FROM prices WHERE instrument_id=? AND as_of_date=? AND source='PRIMARY'",
        [instr_id, prior],
    ).fetchone()
    if prior_price is None:
        return
    gross_per_share = float(prior_price[0]) * div_pct
    announced = _prior_business_day(_prior_business_day(_prior_business_day(d)))

    con.execute(
        "INSERT INTO corporate_actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [f"CA_DEFECT_{spec.defect_id}", instr_id, "SPECIAL_DIV",
         d, d, gross_per_share, None, announced, False],
    )

    # Apply price drop on/after ex-date so the agent can see "stock dropped X%
    # with no news" as a signal.
    con.execute(
        "UPDATE prices SET price = price * ? "
        "WHERE instrument_id=? AND as_of_date >= ?",
        [1.0 - div_pct, instr_id, d],
    )


def _defect_4_stale_price(con, spec: DefectSpec) -> None:
    """Hold LITH price flat for `stale_days` business days, then catch up on
    the as_of date with a `true_drift_pct` drop. Subsequent days inherit the
    drop via a uniform scale factor."""
    instr_id = spec.params.get("instrument_id", "EQ_NS_LITH")
    stale_days = spec.params["stale_days"]
    drop_pct = spec.params["true_drift_pct"]
    d = spec.as_of

    # Find the last good business day BEFORE the stale window starts.
    stale_start = d
    for _ in range(stale_days):
        stale_start = _prior_business_day(stale_start)
    last_good = _prior_business_day(stale_start)

    last_good_price_row = con.execute(
        "SELECT price FROM prices WHERE instrument_id=? AND as_of_date=? AND source='PRIMARY'",
        [instr_id, last_good],
    ).fetchone()
    if last_good_price_row is None:
        return
    last_good_price = float(last_good_price_row[0])

    # Hold flat across stale window.
    cur = stale_start
    for _ in range(stale_days):
        con.execute(
            "UPDATE prices SET price = ? "
            "WHERE instrument_id=? AND as_of_date=? AND source='PRIMARY'",
            [last_good_price, instr_id, cur],
        )
        # Secondary keeps drifting (this is the cross-source signal).
        cur = _next_business_day(cur)

    # Catch-up on as_of date and forward: scale factor relative to factor-model price.
    factor_price_today = con.execute(
        "SELECT price FROM prices WHERE instrument_id=? AND as_of_date=? AND source='PRIMARY'",
        [instr_id, d],
    ).fetchone()
    if factor_price_today is None:
        return
    target_today = last_good_price * (1.0 + drop_pct)
    scale = target_today / float(factor_price_today[0])
    con.execute(
        "UPDATE prices SET price = price * ? "
        "WHERE instrument_id=? AND as_of_date >= ? AND source='PRIMARY'",
        [scale, instr_id, d],
    )


def _defect_7_missed_coupon_accrual(con, spec: DefectSpec) -> None:
    """Hold accrued_interest_pct flat for `missed_days` ending on the as_of
    date for STERL's BARC bond holding. NAV understatement is small (recon
    finding, not a tolerance break)."""
    instr_id = "BND_GBP_BARC_2031"
    missed_days = spec.params["missed_days"]
    d = spec.as_of

    # Get accrual on the day BEFORE the missed window.
    freeze_start = d
    for _ in range(missed_days - 1):
        freeze_start = _prior_business_day(freeze_start)
    last_good = _prior_business_day(freeze_start)

    last_good_acc_row = con.execute(
        "SELECT accrued_interest_pct FROM bond_accruals WHERE instrument_id=? AND as_of_date=?",
        [instr_id, last_good],
    ).fetchone()
    if last_good_acc_row is None:
        return
    frozen = float(last_good_acc_row[0])

    cur = freeze_start
    while cur <= d:
        con.execute(
            "UPDATE bond_accruals SET accrued_interest_pct = ? "
            "WHERE instrument_id=? AND as_of_date=?",
            [frozen, instr_id, cur],
        )
        cur = _next_business_day(cur)


# ----------------------------------------------------------------------------
# POST-walk mutations
# ----------------------------------------------------------------------------
def apply_post_walk_defects(con: duckdb.DuckDBPyConnection) -> None:
    """Surgery on derived tables for behavior-override defects."""
    for spec in DEFECT_SCHEDULE:
        if spec.code == "fx_cutoff_mismatch":
            _defect_2_fx_cutoff(con, spec)
        elif spec.code == "trade_wrong_side":
            _defect_6_trade_flip(con, spec)
        elif spec.code == "subscription_pre_cutoff":
            _defect_8_sub_pre_cutoff(con, spec)
        elif spec.code == "wrong_wht":
            _defect_9_wrong_wht(con, spec)
        elif spec.code == "stale_hwm_perf_fee":
            _defect_5_stale_hwm(con, spec)
        elif spec.code == "class_fee_misallocation":
            _defect_10_class_fee_misallocation(con, spec)


def _defect_2_fx_cutoff(con, spec: DefectSpec) -> None:
    """PACIF used NY_10AM rates instead of policy LDN_4PM on the as-of day.
    Force the JPY intraday move to be exactly the spec value, then recompute
    PACIF holdings + nav for that day."""
    fund_id = spec.fund_id
    fund = _FUND_BY_ID[fund_id]
    d = spec.as_of
    intraday_pct = spec.params["jpy_intraday_move_pct"]

    # Force NY_10AM JPY = LDN_4PM JPY * (1 + intraday_pct). USD/JPY weakened means
    # USD value of JPY assets is lower at NY_10AM relative to LDN_4PM. The wrong
    # snap valued JPY holdings using the (lower) NY_10AM rate, so PACIF NAV is
    # understated by ~intraday_pct * JPY_weight.
    ldn_jpy_row = con.execute(
        "SELECT rate_to_usd FROM fx_rates WHERE as_of_date=? AND ccy='JPY' AND snap='LDN_4PM'",
        [d],
    ).fetchone()
    if ldn_jpy_row is None:
        return
    ldn_jpy = float(ldn_jpy_row[0])
    ny_jpy = ldn_jpy * (1.0 - intraday_pct)
    con.execute(
        "UPDATE fx_rates SET rate_to_usd = ? WHERE as_of_date=? AND ccy='JPY' AND snap='NY_10AM'",
        [ny_jpy, d],
    )

    # Now rewrite PACIF holdings on `d`: anything in JPY uses NY_10AM rate.
    # PACIF base = USD, fund_base_rate_to_usd = 1.0.
    rows = con.execute(
        """
        SELECT h.instrument_id, h.quantity, h.price_local, h.ccy, h.mv_local
        FROM holdings h JOIN instruments i USING (instrument_id)
        WHERE h.fund_id=? AND h.as_of_date=? AND h.ccy='JPY'
        """,
        [fund_id, d],
    ).fetchall()
    new_mv_base_total_for_jpy = 0.0
    old_mv_base_total_for_jpy = 0.0
    for instr_id, qty, price_local, ccy, mv_local in rows:
        new_fx = ny_jpy   # NY_10AM JPY-to-USD
        new_mv_base = float(mv_local) * new_fx
        old_mv_base_row = con.execute(
            "SELECT mv_base, fx_to_base FROM holdings "
            "WHERE fund_id=? AND as_of_date=? AND instrument_id=?",
            [fund_id, d, instr_id],
        ).fetchone()
        old_mv_base_total_for_jpy += float(old_mv_base_row[0])
        new_mv_base_total_for_jpy += new_mv_base
        con.execute(
            "UPDATE holdings SET fx_to_base = ?, mv_base = ? "
            "WHERE fund_id=? AND as_of_date=? AND instrument_id=?",
            [new_fx, new_mv_base, fund_id, d, instr_id],
        )

    # Recompute PACIF nav row for the day.
    delta_base = new_mv_base_total_for_jpy - old_mv_base_total_for_jpy
    _adjust_class_nav(con, fund_id, d, delta_base)


def _defect_5_stale_hwm(con, spec: DefectSpec) -> None:
    """Override COBAL Class I HWM to a stale lower value, recompute perf
    fee accrual, and adjust NAV downward by the over-accrual."""
    fund_id = spec.fund_id
    cls = spec.share_class
    d = spec.as_of
    stale_offset = spec.params["stale_hwm_offset_pct"]

    initial_nav_row = con.execute(
        "SELECT initial_nav_per_share FROM share_classes WHERE fund_id=? AND class_code=?",
        [fund_id, cls],
    ).fetchone()
    initial_nav = float(initial_nav_row[0])
    stale_hwm = initial_nav * (1.0 + stale_offset)

    # Pull current state on date d.
    nav_row = con.execute(
        "SELECT shares_outstanding, nav_per_share, prior_nav_per_share, gav_base, fees_accrued, nav_base "
        "FROM nav WHERE fund_id=? AND class_code=? AND as_of_date=?",
        [fund_id, cls, d],
    ).fetchone()
    if nav_row is None:
        return
    shares, nav_ps, prior_nav_ps, gav, fees_today, nav_base = nav_row

    fee_row = con.execute(
        "SELECT mgmt_fee_daily, perf_fee_delta, perf_fee_balance, hwm_nav_per_share "
        "FROM fee_accruals WHERE fund_id=? AND class_code=? AND as_of_date=?",
        [fund_id, cls, d],
    ).fetchone()
    if fee_row is None:
        return
    mgmt_fee, _orig_perf_delta, orig_perf_balance, _orig_hwm = fee_row

    sc_row = con.execute(
        "SELECT perf_fee_bps FROM share_classes WHERE fund_id=? AND class_code=?",
        [fund_id, cls],
    ).fetchone()
    perf_rate = float(sc_row[0]) / 10000.0

    # Re-derive pre-perf-fee NAV per share (was used to compute the original
    # perf fee). Reverse from nav: post_perf_aum = nav_base; pre_perf_aum =
    # post_perf_aum + orig_perf_balance.
    post_perf_aum = float(nav_base)
    pre_perf_aum = post_perf_aum + float(orig_perf_balance)
    pre_perf_nav = pre_perf_aum / float(shares)

    new_target_balance = max(
        0.0, (pre_perf_nav - stale_hwm) * float(shares) * perf_rate,
    )
    new_perf_fee_delta = new_target_balance - float(orig_perf_balance) + float(_orig_perf_delta) - float(orig_perf_balance)
    # Simpler: don't try to chain; just store the new state.
    new_post_perf_aum = pre_perf_aum - new_target_balance
    new_nav_per_share = new_post_perf_aum / float(shares)

    con.execute(
        """
        UPDATE fee_accruals
           SET perf_fee_balance = ?,
               perf_fee_delta   = ?,
               hwm_nav_per_share = ?
         WHERE fund_id=? AND class_code=? AND as_of_date=?
        """,
        [
            float(new_target_balance),
            float(new_target_balance - 0.0),  # delta from prior (treated as 0 baseline for v0)
            float(stale_hwm),
            fund_id, cls, d,
        ],
    )

    new_move_bps = ((new_nav_per_share / float(prior_nav_ps)) - 1.0) * 1e4
    new_is_break = abs(new_move_bps) > _FUND_BY_ID[fund_id].tolerance_bps
    new_fees_accrued = float(mgmt_fee) + float(new_target_balance)
    con.execute(
        """
        UPDATE nav
           SET nav_base = ?, nav_per_share = ?, fees_accrued = ?,
               nav_move_bps = ?, is_break = ?
         WHERE fund_id=? AND class_code=? AND as_of_date=?
        """,
        [
            float(new_post_perf_aum),
            float(new_nav_per_share),
            float(new_fees_accrued),
            float(new_move_bps),
            bool(new_is_break),
            fund_id, cls, d,
        ],
    )


def _defect_6_trade_flip(con, spec: DefectSpec) -> None:
    """Flip the side of the largest HELIO trade on the as-of date AFTER the
    walk has already booked holdings/cash from the original side. Result:
    trade row says SELL but holdings show position went UP (recon mismatch)."""
    fund_id = spec.fund_id
    d = spec.as_of
    rows = con.execute(
        """
        SELECT trade_id, side, quantity, price
        FROM trades WHERE fund_id=? AND trade_date=?
        ORDER BY (quantity * price) DESC
        """,
        [fund_id, d],
    ).fetchall()
    if not rows:
        # No trade today; insert one we can flip.
        return
    trade_id, side, _qty, _price = rows[0]
    new_side = "SELL" if side == "BUY" else "BUY"
    con.execute(
        "UPDATE trades SET side=?, booking_note=? WHERE trade_id=?",
        [new_side, "DEFECT_6_FLIPPED_FROM_" + side, trade_id],
    )


def _defect_8_sub_pre_cutoff(con, spec: DefectSpec) -> None:
    """ATLAS Class A had a $50M subscription on the as-of date that was
    stamped pre-cutoff but actually arrived post-cutoff. The system priced
    the sub at TODAY's NAV; per dealing rules it should have been priced at
    TOMORROW's NAV. Inverted dilution math: existing holders received fewer
    shares than they should have (or alternatively the new subscriber got
    more). To produce the dilution the demo wants, we reprice the sub at
    YESTERDAY's NAV instead -- representing a system that mistakenly
    priced before the day's market move."""
    fund_id = spec.fund_id
    cls = spec.share_class
    d = spec.as_of
    sub_amount = spec.params["sub_amount_usd"]
    intraday_market = spec.params.get("intraday_market_pct", 0.020)

    # Look up prior business day NAV for the class, then force a positive
    # market-move on `d` by amplifying that day's nav move and finally apply
    # the dilution from a sub priced at the prior NAV.
    prior = _prior_business_day(d)
    prior_nav_row = con.execute(
        "SELECT nav_per_share FROM nav WHERE fund_id=? AND class_code=? AND as_of_date=?",
        [fund_id, cls, prior],
    ).fetchone()
    if prior_nav_row is None:
        return
    prior_nav = float(prior_nav_row[0])

    today_row = con.execute(
        "SELECT nav_per_share, shares_outstanding, nav_base, gav_base, fees_accrued FROM nav "
        "WHERE fund_id=? AND class_code=? AND as_of_date=?",
        [fund_id, cls, d],
    ).fetchone()
    if today_row is None:
        return
    today_nav, today_shares, today_nav_base, today_gav, today_fees = today_row

    # Step 1: simulate the +X% market gain on Class A's NAV (override).
    nav_after_gain = prior_nav * (1.0 + intraday_market)
    # AUM after gain (before sub): existing_shares_pre_sub * nav_after_gain.
    # Existing shares pre-sub = today's shares - whatever sub-shares were originally booked.
    existing_subs_today = con.execute(
        """
        SELECT COALESCE(SUM(shares_delta), 0)
        FROM capstock WHERE fund_id=? AND class_code=? AND as_of_date=?
        """,
        [fund_id, cls, d],
    ).fetchone()[0]
    shares_pre_sub = float(today_shares) - float(existing_subs_today or 0.0)
    aum_after_gain = shares_pre_sub * nav_after_gain

    # Step 2: insert defect sub at prior NAV (the wrong price).
    new_sub_shares = sub_amount / prior_nav
    new_total_shares = shares_pre_sub + new_sub_shares
    new_total_aum = aum_after_gain + sub_amount
    new_nav_per_share = new_total_aum / new_total_shares

    # Insert capstock event for the defect sub.
    cap_id = f"CS_DEFECT_{spec.defect_id}"
    from datetime import datetime as _dt, time as _t
    order_ts = _dt.combine(d, _t(13, 30))
    cutoff_ts = _dt.combine(d, _t(12, 0))
    con.execute(
        "INSERT INTO capstock VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [cap_id, fund_id, cls, d, order_ts, cutoff_ts, d, "SUB",
         float(sub_amount), float(new_sub_shares)],
    )

    # Step 3: rewrite nav row for ATLAS Class A on d.
    prior_nav_for_move = prior_nav
    new_move_bps = ((new_nav_per_share / prior_nav_for_move) - 1.0) * 1e4
    new_is_break = abs(new_move_bps) > _FUND_BY_ID[fund_id].tolerance_bps
    con.execute(
        """
        UPDATE nav SET nav_per_share=?, shares_outstanding=?, nav_base=?,
                       nav_move_bps=?, is_break=?, prior_nav_per_share=?
         WHERE fund_id=? AND class_code=? AND as_of_date=?
        """,
        [
            float(new_nav_per_share), float(new_total_shares), float(new_total_aum),
            float(new_move_bps), bool(new_is_break), float(prior_nav_for_move),
            fund_id, cls, d,
        ],
    )


def _defect_9_wrong_wht(con, spec: DefectSpec) -> None:
    """AURORA received a Samsung dividend on the as-of date with WHT applied
    at the Korean statutory rate (22%) instead of the LU-Korea treaty rate
    (15%). 7% gap of gross dividend is missing from cash."""
    fund_id = spec.fund_id
    d = spec.as_of
    instr_id = "EQ_EM_SAMSU"
    treaty_rate = spec.params["treaty_rate"]
    applied_rate = spec.params["applied_rate"]

    # Make sure a dividend exists on this date for Samsung in our universe;
    # if not, insert a synthetic CA + dividend_receipt.
    qty = con.execute(
        "SELECT quantity FROM holdings WHERE fund_id=? AND instrument_id=? AND as_of_date=?",
        [fund_id, instr_id, d],
    ).fetchone()
    if not qty or float(qty[0]) <= 0:
        return
    qty = float(qty[0])

    # Pull Samsung price on d to size the dividend.
    p_row = con.execute(
        "SELECT price FROM prices WHERE instrument_id=? AND as_of_date=? AND source='PRIMARY'",
        [instr_id, d],
    ).fetchone()
    if p_row is None:
        return
    price = float(p_row[0])
    div_pct = 0.018  # ~1.8% Samsung div yield is realistic
    gross_per_share = price * div_pct
    gross_local = qty * gross_per_share
    wht_amount = gross_local * applied_rate
    net_local = gross_local - wht_amount

    # Insert CA (applied=True so walk would have processed it had we re-walked;
    # we inject post-walk so we also book the receipt manually with the wrong rate.)
    ca_id = f"CA_DEFECT_{spec.defect_id}"
    con.execute(
        "INSERT INTO corporate_actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [ca_id, instr_id, "CASH_DIV", d, d, gross_per_share, None,
         _prior_business_day(_prior_business_day(d)), True],
    )
    receipt_id = f"DR_DEFECT_{spec.defect_id}"
    con.execute(
        "INSERT INTO dividend_receipts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [receipt_id, fund_id, instr_id, d, "KRW",
         float(gross_local), float(applied_rate), float(wht_amount), float(net_local)],
    )

    # Adjust AURORA NAV for missed reclaimable amount.
    over_wht = (applied_rate - treaty_rate) * gross_local
    fx_to_usd_row = con.execute(
        "SELECT rate_to_usd FROM fx_rates WHERE as_of_date=? AND ccy='KRW' AND snap='LDN_4PM'",
        [d],
    ).fetchone()
    if fx_to_usd_row is None:
        return
    over_wht_usd = over_wht * float(fx_to_usd_row[0])
    _adjust_class_nav(con, fund_id, d, -over_wht_usd)


def _defect_10_class_fee_misallocation(con, spec: DefectSpec) -> None:
    """ATLAS Class I gets charged Class A's mgmt fee for the day in addition
    to its own. Recompute Class I NAV down by the extra fee."""
    fund_id = spec.fund_id
    target_cls = spec.share_class
    source_cls = spec.params["misallocated_from"]
    d = spec.as_of

    src_fee_row = con.execute(
        "SELECT mgmt_fee_daily FROM fee_accruals "
        "WHERE fund_id=? AND class_code=? AND as_of_date=?",
        [fund_id, source_cls, d],
    ).fetchone()
    if src_fee_row is None:
        return
    src_fee = float(src_fee_row[0])

    nav_row = con.execute(
        "SELECT nav_base, nav_per_share, shares_outstanding, prior_nav_per_share, fees_accrued FROM nav "
        "WHERE fund_id=? AND class_code=? AND as_of_date=?",
        [fund_id, target_cls, d],
    ).fetchone()
    if nav_row is None:
        return
    nav_base, nav_ps, shares, prior_nav_ps, fees_accrued = nav_row

    # Apply 10x overcharge so it clearly lands above tolerance for the demo.
    extra_fee = src_fee * 10.0
    new_nav_base = float(nav_base) - extra_fee
    new_nav_ps = new_nav_base / float(shares)
    new_move_bps = ((new_nav_ps / float(prior_nav_ps)) - 1.0) * 1e4
    new_is_break = abs(new_move_bps) > _FUND_BY_ID[fund_id].tolerance_bps

    con.execute(
        """
        UPDATE nav SET nav_base=?, nav_per_share=?, fees_accrued=?,
                       nav_move_bps=?, is_break=?
         WHERE fund_id=? AND class_code=? AND as_of_date=?
        """,
        [
            float(new_nav_base), float(new_nav_ps),
            float(fees_accrued) + extra_fee,
            float(new_move_bps), bool(new_is_break),
            fund_id, target_cls, d,
        ],
    )
    # Augment fee row.
    con.execute(
        "UPDATE fee_accruals SET mgmt_fee_daily = mgmt_fee_daily + ? "
        "WHERE fund_id=? AND class_code=? AND as_of_date=?",
        [extra_fee, fund_id, target_cls, d],
    )


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def _next_business_day(d: date) -> date:
    cur = d + timedelta(days=1)
    while cur.weekday() >= 5:
        cur += timedelta(days=1)
    return cur


def _adjust_class_nav(con, fund_id: str, d: date, delta_base: float) -> None:
    """Apply `delta_base` (in fund base ccy) pro-rata across share classes
    of the fund on date `d`. Recompute nav_per_share, move_bps, is_break."""
    rows = con.execute(
        "SELECT class_code, nav_base, shares_outstanding, prior_nav_per_share "
        "FROM nav WHERE fund_id=? AND as_of_date=?",
        [fund_id, d],
    ).fetchall()
    total_aum = sum(float(r[1]) for r in rows)
    if total_aum <= 0:
        return
    fund = _FUND_BY_ID[fund_id]
    for cc, nav_base, shares, prior_nav_ps in rows:
        share_of = float(nav_base) / total_aum
        cls_delta = delta_base * share_of
        new_nav_base = float(nav_base) + cls_delta
        new_nav_ps = new_nav_base / float(shares)
        new_move_bps = ((new_nav_ps / float(prior_nav_ps)) - 1.0) * 1e4
        new_is_break = abs(new_move_bps) > fund.tolerance_bps
        con.execute(
            """
            UPDATE nav SET nav_base=?, nav_per_share=?, nav_move_bps=?, is_break=?
             WHERE fund_id=? AND class_code=? AND as_of_date=?
            """,
            [
                float(new_nav_base), float(new_nav_ps),
                float(new_move_bps), bool(new_is_break),
                fund_id, cc, d,
            ],
        )


def update_defect_catalog_with_realized_impact(con: duckdb.DuckDBPyConnection) -> None:
    """Compute realized bps impact per defect by reading the affected NAV row
    and store it into defect_catalog.expected_bps_impact for the verification
    report."""
    for spec in DEFECT_SCHEDULE:
        if spec.share_class:
            row = con.execute(
                "SELECT nav_move_bps FROM nav WHERE fund_id=? AND class_code=? AND as_of_date=?",
                [spec.fund_id, spec.share_class, spec.as_of],
            ).fetchone()
        else:
            row = con.execute(
                "SELECT AVG(nav_move_bps) FROM nav WHERE fund_id=? AND as_of_date=?",
                [spec.fund_id, spec.as_of],
            ).fetchone()
        if row is None or row[0] is None:
            continue
        con.execute(
            "UPDATE defect_catalog SET expected_bps_impact=? WHERE defect_id=?",
            [float(row[0]), spec.defect_id],
        )
