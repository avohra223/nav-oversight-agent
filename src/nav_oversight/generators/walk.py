"""Walk-forward NAV computation.

Given the static reference data + time series + trade/CA/capstock event logs
already in DuckDB, this module walks day-by-day per fund computing:
  - holdings (qty, mv_local, mv_base) per instrument
  - fund-level cash in base ccy
  - per-class fee accruals (mgmt + perf with HWM)
  - per-class shares outstanding and NAV per share
  - dividend receipts (with treaty-correct WHT)

It also writes shares_delta back into the capstock rows and finalizes trade
prices using day-of PRIMARY market price.

Simplifications (v0):
  - All trades settle T+0 (cash impact same day as trade).
  - Cash is kept in fund base ccy only (no FC cash ledger).
  - Mgmt + perf fee accruals reduce fund cash directly each day (model
    shortcut; real funds carry these as liabilities, but the NAV math is
    equivalent at this resolution).
  - HWM is held static at initial NAV per share through the window
    (crystallization typically annual). Defect 5 will mutate it.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

import duckdb

from ..config import FUNDS, FX_VS_USD_INITIAL, Fund, ShareClass
from .reference import ALL_INSTRUMENTS, FUND_DOMICILES, get_wht_rates


_INSTRUMENT_BY_ID = {i.instrument_id: i for i in ALL_INSTRUMENTS}


# ---------------------------------------------------------------------------
# Loading helpers (read what previous generators wrote into DuckDB into memory).
# ---------------------------------------------------------------------------
def _load_prices_primary(con) -> dict[date, dict[str, float]]:
    rows = con.execute(
        "SELECT as_of_date, instrument_id, price FROM prices WHERE source='PRIMARY'"
    ).fetchall()
    out: dict[date, dict[str, float]] = defaultdict(dict)
    for d, iid, p in rows:
        out[d][iid] = p
    return out


def _load_bond_accruals(con) -> dict[date, dict[str, float]]:
    rows = con.execute(
        "SELECT as_of_date, instrument_id, accrued_interest_pct FROM bond_accruals"
    ).fetchall()
    out: dict[date, dict[str, float]] = defaultdict(dict)
    for d, iid, a in rows:
        out[d][iid] = a
    return out


def _load_fx(con, snap: str) -> dict[date, dict[str, float]]:
    rows = con.execute(
        "SELECT as_of_date, ccy, rate_to_usd FROM fx_rates WHERE snap = ?",
        [snap],
    ).fetchall()
    out: dict[date, dict[str, float]] = defaultdict(dict)
    for d, c, r in rows:
        out[d][c] = r
    return out


def _fx_to_base(rate_to_usd_src: float, rate_to_usd_base: float) -> float:
    """Multiplier converting 1 unit of source ccy to fund base ccy."""
    return rate_to_usd_src / rate_to_usd_base


def _load_corporate_actions(con) -> dict[date, list[tuple]]:
    rows = con.execute(
        "SELECT ca_id, instrument_id, ca_type, ex_date, pay_date, gross_amount, applied_flag "
        "FROM corporate_actions"
    ).fetchall()
    out: dict[date, list[tuple]] = defaultdict(list)
    for r in rows:
        out[r[4]].append(r)   # key by pay_date
    return out


def _load_trades(con) -> dict[tuple[str, date], list[tuple]]:
    rows = con.execute(
        "SELECT trade_id, fund_id, instrument_id, side, quantity, ccy, trade_date "
        "FROM trades"
    ).fetchall()
    out: dict[tuple[str, date], list[tuple]] = defaultdict(list)
    for r in rows:
        out[(r[1], r[6])].append(r)
    return out


def _load_capstock(con) -> dict[tuple[str, str, date], list[tuple]]:
    rows = con.execute(
        "SELECT capstock_id, fund_id, class_code, as_of_date, flow_type, gross_amount_base "
        "FROM capstock"
    ).fetchall()
    out: dict[tuple[str, str, date], list[tuple]] = defaultdict(list)
    for r in rows:
        out[(r[1], r[2], r[3])].append(r)
    return out


# ---------------------------------------------------------------------------
# Walk state
# ---------------------------------------------------------------------------
@dataclass
class FundState:
    fund: Fund
    holdings: dict[str, float] = field(default_factory=dict)   # instr_id -> qty
    cash_base: float = 0.0
    class_state: dict[str, "ClassState"] = field(default_factory=dict)
    prior_total_aum: float = 0.0


@dataclass
class ClassState:
    code: str
    cfg: ShareClass
    shares: float
    nav_per_share: float
    perf_fee_balance: float
    hwm: float


# ---------------------------------------------------------------------------
# Initialization from portfolio_init output
# ---------------------------------------------------------------------------
def _init_fund_state(fund: Fund, portfolio) -> FundState:
    state = FundState(fund=fund)
    for instr_id, qty, _price in portfolio.holdings:
        state.holdings[instr_id] = qty
    state.cash_base = portfolio.cash_base
    for c in fund.classes:
        state.class_state[c.code] = ClassState(
            code=c.code,
            cfg=c,
            shares=c.initial_shares,
            nav_per_share=c.initial_nav_per_share,
            perf_fee_balance=0.0,
            hwm=c.initial_nav_per_share,
        )
    state.prior_total_aum = portfolio.initial_aum_base
    return state


# ---------------------------------------------------------------------------
# Per-day update
# ---------------------------------------------------------------------------
def _step_one_day(
    state: FundState,
    d: date,
    prices_today: dict[str, float],
    accruals_today: dict[str, float],
    fx_today: dict[str, float],
    fund_base_rate_to_usd: float,
    trades_today: list[tuple],
    cas_today: list[tuple],
    capstock_today_by_class: dict[str, list[tuple]],
    holdings_rows: list,
    cash_rows: list,
    fee_rows: list,
    nav_rows: list,
    div_receipt_rows: list,
    trade_finalizations: list,
    capstock_finalizations: list,
    domicile: str,
) -> None:
    fund = state.fund

    # 1. Apply trades on date d. Update holdings + cash.
    for trade in trades_today:
        trade_id, _fund_id, instr_id, side, qty, ccy, _td = trade
        instr = _INSTRUMENT_BY_ID[instr_id]
        if instr_id not in prices_today:
            continue
        price_local = prices_today[instr_id]
        # Update holdings
        signed_qty = qty if side == "BUY" else -qty
        state.holdings[instr_id] = state.holdings.get(instr_id, 0.0) + signed_qty
        # Cash impact: BUY drains cash, SELL credits it.
        if instr.type == "BOND":
            notional_local = qty * (price_local + accruals_today.get(instr_id, 0.0)) / 100.0 * (instr.face_value or 100.0)
        else:
            notional_local = qty * price_local
        rate_to_usd_src = fx_today[ccy]
        notional_base = notional_local * _fx_to_base(rate_to_usd_src, fund_base_rate_to_usd)
        if side == "BUY":
            state.cash_base -= notional_base
        else:
            state.cash_base += notional_base
        trade_finalizations.append((trade_id, price_local))

    # 2. Compute mv_securities at today's prices + fx.
    mv_securities = 0.0
    instr_rows: list[tuple] = []
    for instr_id, qty in list(state.holdings.items()):
        if abs(qty) < 1e-9:
            continue
        instr = _INSTRUMENT_BY_ID[instr_id]
        if instr_id not in prices_today:
            continue
        price_local = prices_today[instr_id]
        if instr.type == "BOND":
            accrued = accruals_today.get(instr_id, 0.0)
            mv_local = qty * (price_local + accrued) / 100.0 * (instr.face_value or 100.0)
        else:
            mv_local = qty * price_local
        rate_to_usd_src = fx_today[instr.ccy]
        fx_to_base_mult = _fx_to_base(rate_to_usd_src, fund_base_rate_to_usd)
        mv_base = mv_local * fx_to_base_mult
        mv_securities += mv_base
        instr_rows.append((d, fund.fund_id, instr_id, qty, price_local, instr.ccy,
                           mv_local, fx_to_base_mult, mv_base))

    # 3. Apply CA cash receipts (pay_date == d, applied_flag True).
    for ca in cas_today:
        ca_id, instr_id, ca_type, _ex_date, _pay_date, gross_per_share, applied = ca
        if not applied:
            continue
        qty = state.holdings.get(instr_id, 0.0)
        if qty <= 0:
            continue
        instr = _INSTRUMENT_BY_ID[instr_id]
        gross_local = qty * (gross_per_share or 0.0)
        treaty, statutory = get_wht_rates(domicile, instr.country)
        wht_rate_used = treaty
        wht_amount = gross_local * wht_rate_used
        net_local = gross_local - wht_amount
        rate_to_usd_src = fx_today[instr.ccy]
        net_base = net_local * _fx_to_base(rate_to_usd_src, fund_base_rate_to_usd)
        state.cash_base += net_base
        receipt_id = f"DR_{fund.fund_id}_{ca_id}"
        div_receipt_rows.append((
            receipt_id, fund.fund_id, instr_id, d, instr.ccy,
            float(gross_local), float(wht_rate_used), float(wht_amount), float(net_local),
        ))

    # 4. Fund total assets pre-fee, pre-capstock.
    fund_total_assets = mv_securities + state.cash_base

    # 5. Allocate fund return to classes. r = fund_total_assets / prior_total_aum - 1.
    # We then walk per class, applying fees and capstock.
    if state.prior_total_aum <= 0:
        r_fund = 0.0
    else:
        r_fund = fund_total_assets / state.prior_total_aum - 1.0

    new_total_aum = 0.0
    for code, cs in state.class_state.items():
        prior_aum = cs.shares * cs.nav_per_share
        post_market_aum = prior_aum * (1.0 + r_fund)

        # Mgmt fee daily.
        mgmt_fee = post_market_aum * (cs.cfg.mgmt_fee_bps / 10000.0) / 365.0
        post_mgmt_aum = post_market_aum - mgmt_fee
        pre_perf_nav_per_share = post_mgmt_aum / cs.shares

        # Perf fee logic.
        if cs.cfg.has_hwm:
            target_balance = max(
                0.0,
                (pre_perf_nav_per_share - cs.hwm) * cs.shares * (cs.cfg.perf_fee_bps / 10000.0),
            )
            perf_fee_delta = target_balance - cs.perf_fee_balance
            post_perf_aum = post_mgmt_aum - target_balance
            cs.perf_fee_balance = target_balance
        else:
            target_balance = 0.0
            perf_fee_delta = 0.0
            post_perf_aum = post_mgmt_aum

        nav_after_fees = post_perf_aum / cs.shares
        # Note: HWM is held static through the window for v0.

        # Apply capstock at post-fee NAV.
        shares_delta_total = 0.0
        capstock_cash_in = 0.0
        for cap in capstock_today_by_class.get(code, []):
            cap_id, _fund_id, _class_code, _as_of, flow_type, gross = cap
            if flow_type == "SUB":
                sd = gross / nav_after_fees
            else:
                sd = -gross / nav_after_fees
            shares_delta_total += sd
            capstock_cash_in += (gross if flow_type == "SUB" else -gross)
            capstock_finalizations.append((cap_id, sd, nav_after_fees))

        shares_post = cs.shares + shares_delta_total
        # New class AUM = nav_after_fees * shares_post (capstock at NAV doesn't move NAV).
        new_class_aum = nav_after_fees * shares_post

        # Update fund cash for capstock + fees.
        state.cash_base += capstock_cash_in - mgmt_fee - perf_fee_delta

        # Class fee row.
        fee_rows.append((
            d, fund.fund_id, code,
            float(mgmt_fee), float(perf_fee_delta),
            float(cs.perf_fee_balance), float(cs.hwm),
        ))

        # NAV row.
        prior_nav_per_share = cs.nav_per_share
        nav_move_bps = ((nav_after_fees / prior_nav_per_share) - 1.0) * 1e4 if prior_nav_per_share > 0 else 0.0
        is_break = abs(nav_move_bps) > fund.tolerance_bps
        nav_rows.append((
            d, fund.fund_id, code,
            float(post_market_aum),                # gav_base (post-market AUM, pre-fees)
            float(mgmt_fee + target_balance),      # fees_accrued today (mgmt today + perf balance)
            float(new_class_aum),                  # nav_base (post-fee, post-capstock class AUM)
            float(shares_post),
            float(nav_after_fees),
            float(prior_nav_per_share),
            float(nav_move_bps),
            bool(is_break),
        ))

        # Persist updated class state.
        cs.shares = shares_post
        cs.nav_per_share = nav_after_fees
        new_total_aum += new_class_aum

    state.prior_total_aum = new_total_aum

    # Holdings rows.
    holdings_rows.extend(instr_rows)

    # Cash row (single base ccy).
    cash_rows.append((d, fund.fund_id, fund.base_ccy, float(state.cash_base)))


# ---------------------------------------------------------------------------
# Top-level driver
# ---------------------------------------------------------------------------
def walk_forward(con: duckdb.DuckDBPyConnection, dates: list[date]) -> None:
    from .portfolio_init import all_initial_portfolios

    portfolios = all_initial_portfolios()
    fx_ldn = _load_fx(con, "LDN_4PM")
    prices = _load_prices_primary(con)
    accruals = _load_bond_accruals(con)
    cas_by_paydate = _load_corporate_actions(con)
    trades_by_fund_date = _load_trades(con)
    capstock_by_fund_class_date = _load_capstock(con)

    # Initial state per fund.
    states = {f.fund_id: _init_fund_state(f, portfolios[f.fund_id]) for f in FUNDS}

    # Day 0 (first date in `dates`) is special: holdings are the initial portfolio,
    # but we still want a row in holdings/cash/nav for that date. For simplicity
    # we step day-by-day starting from dates[0] using a "synthetic" prior state.
    # Easier approach: treat dates[0] as a regular step but with prior_total_aum
    # already correct and no trades / capstock / CAs assumed inside it (in case
    # any happen, they apply naturally).

    # Bucket capstock by class (within fund-day key).
    def capstock_for(fund_id: str, d: date) -> dict[str, list[tuple]]:
        out: dict[str, list[tuple]] = defaultdict(list)
        for f in FUNDS:
            if f.fund_id != fund_id:
                continue
            for c in f.classes:
                evs = capstock_by_fund_class_date.get((fund_id, c.code, d), [])
                if evs:
                    out[c.code] = evs
        return out

    holdings_rows: list = []
    cash_rows: list = []
    fee_rows: list = []
    nav_rows: list = []
    div_receipt_rows: list = []
    trade_finalizations: list = []
    capstock_finalizations: list = []

    for d in dates:
        if d not in fx_ldn:
            continue
        fx_today = fx_ldn[d]
        prices_today = prices.get(d, {})
        accruals_today = accruals.get(d, {})
        cas_today = cas_by_paydate.get(d, [])

        for f in FUNDS:
            state = states[f.fund_id]
            fund_base_rate = fx_today[f.base_ccy]
            trades_today = trades_by_fund_date.get((f.fund_id, d), [])
            cap_today_by_class = capstock_for(f.fund_id, d)
            domicile = FUND_DOMICILES[f.fund_id]
            _step_one_day(
                state=state,
                d=d,
                prices_today=prices_today,
                accruals_today=accruals_today,
                fx_today=fx_today,
                fund_base_rate_to_usd=fund_base_rate,
                trades_today=trades_today,
                cas_today=cas_today,
                capstock_today_by_class=cap_today_by_class,
                holdings_rows=holdings_rows,
                cash_rows=cash_rows,
                fee_rows=fee_rows,
                nav_rows=nav_rows,
                div_receipt_rows=div_receipt_rows,
                trade_finalizations=trade_finalizations,
                capstock_finalizations=capstock_finalizations,
                domicile=domicile,
            )

    # Bulk write.
    con.executemany(
        "INSERT INTO holdings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", holdings_rows,
    )
    con.executemany(
        "INSERT INTO cash VALUES (?, ?, ?, ?)", cash_rows,
    )
    con.executemany(
        "INSERT INTO fee_accruals VALUES (?, ?, ?, ?, ?, ?, ?)", fee_rows,
    )
    con.executemany(
        "INSERT INTO nav VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", nav_rows,
    )
    con.executemany(
        "INSERT INTO dividend_receipts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        div_receipt_rows,
    )

    # Update trade prices.
    if trade_finalizations:
        con.executemany(
            "UPDATE trades SET price = ? WHERE trade_id = ?",
            [(p, tid) for tid, p in trade_finalizations],
        )

    # Update capstock shares_delta.
    if capstock_finalizations:
        con.executemany(
            "UPDATE capstock SET shares_delta = ? WHERE capstock_id = ?",
            [(sd, cid) for cid, sd, _nav in capstock_finalizations],
        )
