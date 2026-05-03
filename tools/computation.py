"""Pure computation tools.

These functions take raw inputs (numbers, lists, dataclasses already fetched
by the caller) and return raw outputs. They do NOT touch the database.

Each function is a single arithmetic / structural transform. The agent
composes them with the DB-querying tools to draw conclusions.

Note: detect_flat_run_in_series is named with the `detect_` prefix because
the user requested that name explicitly. It is structurally a fact-returner
(it reports WHERE the series is flat, never WHETHER that's wrong) -- the
hygiene linter knows to skip this name.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Sequence

from ._audit import audit_tool
from ._types import AttributionLine, FlatRunSegment, Holding


@audit_tool
def compute_implied_dividend_return(
    gross_amount: float, pre_ex_price: float
) -> float:
    """Return the price-drop fraction implied by a per-share dividend.

    A correctly-applied cash dividend would push the ex-date close down by
    approximately gross_amount / pre_ex_price. The returned number is
    NEGATIVE (a price drop). The caller compares to the realized return.

    Raises ValueError if pre_ex_price <= 0.

    Example:
        compute_implied_dividend_return(2.50, 200.0)  -> -0.0125
    """
    if pre_ex_price <= 0:
        raise ValueError(f"pre_ex_price must be > 0, got {pre_ex_price}")
    return -float(gross_amount) / float(pre_ex_price)


@audit_tool
def compute_implied_wht_rate(gross_amount: float, wht_amount: float) -> float:
    """Return the WHT rate implied by gross and withheld amounts.

    Useful for sanity checks and for cases where wht_rate_used isn't trusted.

    Raises ValueError if gross_amount <= 0.

    Example:
        compute_implied_wht_rate(1000.0, 220.0)  -> 0.22
    """
    if gross_amount <= 0:
        raise ValueError(f"gross_amount must be > 0, got {gross_amount}")
    return float(wht_amount) / float(gross_amount)


@audit_tool
def compute_expected_coupon_accrual(
    face_value: float,
    coupon_rate: float,
    day_count_convention: str,
    days: int,
) -> float:
    """Return expected coupon accrual amount over `days` days.

    Schema: returns a float in the bond's currency (face_value units).

    Day count conventions supported in v0:
      - 'ACT/365':   amount = face * coupon_rate * days / 365
      - 'ACT/360':   amount = face * coupon_rate * days / 360
      - '30/360':    amount = face * coupon_rate * days / 360 (treats months as 30d)

    Raises ValueError on unknown convention.

    Example:
        compute_expected_coupon_accrual(100.0, 0.055, 'ACT/365', 4)  -> 0.0603
    """
    days = int(days)
    rate = float(coupon_rate)
    fv = float(face_value)
    conv = day_count_convention.upper()
    if conv == "ACT/365":
        return fv * rate * days / 365.0
    if conv in ("ACT/360", "30/360"):
        return fv * rate * days / 360.0
    raise ValueError(f"unsupported day_count_convention: {day_count_convention}")


@audit_tool
def compute_perf_fee(
    nav_per_share: float,
    hwm_nav_per_share: float,
    hurdle_bps: int,
    perf_fee_bps: int,
    period_days: int,
) -> float:
    """Compute the performance fee owed PER SHARE under a HWM-with-hurdle model.

    Schema: returns a non-negative float (fee per share, in fund base ccy).

    The hurdle is annualized in bps and pro-rated over period_days using
    ACT/365. Fee is on returns above (HWM * (1 + hurdle * period_days/365)).
    If nav_per_share <= the hurdle-adjusted HWM, returns 0.

    Example (no hurdle):
        compute_perf_fee(110, 100, 0, 2000, 365)  -> 2.0  (20% of 10)
    Example (with hurdle):
        compute_perf_fee(110, 100, 500, 2000, 365)  -> 1.0
        # hurdle = 100 * 1.05 = 105; fee on (110-105)*0.20 = 1.0
    """
    if nav_per_share < 0 or hwm_nav_per_share < 0:
        raise ValueError("nav and hwm must be >= 0")
    if perf_fee_bps < 0:
        raise ValueError("perf_fee_bps must be >= 0")
    hurdle_adj = float(hwm_nav_per_share) * (
        1.0 + (hurdle_bps / 10000.0) * period_days / 365.0
    )
    profit_per_share = max(0.0, float(nav_per_share) - hurdle_adj)
    return profit_per_share * (perf_fee_bps / 10000.0)


@audit_tool
def compute_attribution(
    holdings_t: Sequence[Holding],
    holdings_t_minus_1: Sequence[Holding],
    prices_t: dict[str, float],
    prices_t_minus_1: dict[str, float],
) -> list[AttributionLine]:
    """Per-instrument contribution to fund return between t-1 and t.

    Contribution_local = qty_t-1 * (price_t - price_t-1)

    Returns one AttributionLine per instrument that appears in either
    holdings list or both price dicts. Quantities/prices missing on one
    side are treated as 0 (a position opened or closed contributes nothing
    on the day before/after it existed).

    Schema (per row): AttributionLine(instrument_id, qty_t_minus_1,
    price_t_minus_1, price_t, contribution_local).

    Does NOT convert to base currency, normalize against fund AUM, or
    classify "what drove the move." The caller does that.

    Example:
        attribution = compute_attribution(today_h, yesterday_h, p_t, p_y)
    """
    qty_prev = {h.instrument_id: float(h.quantity) for h in holdings_t_minus_1}
    qty_today = {h.instrument_id: float(h.quantity) for h in holdings_t}
    universe = set(qty_prev) | set(qty_today) | set(prices_t) | set(prices_t_minus_1)
    out: list[AttributionLine] = []
    for instr in sorted(universe):
        q_prev = qty_prev.get(instr, 0.0)
        p_prev = float(prices_t_minus_1.get(instr, 0.0))
        p_t = float(prices_t.get(instr, 0.0))
        contribution = q_prev * (p_t - p_prev)
        out.append(AttributionLine(
            instrument_id=instr,
            qty_t_minus_1=q_prev,
            price_t_minus_1=p_prev,
            price_t=p_t,
            contribution_local=contribution,
        ))
    return out


@audit_tool
def detect_flat_run_in_series(
    series: Sequence[tuple[date, float]],
    min_length_days: int,
    tolerance: float = 1e-9,
) -> list[FlatRunSegment]:
    """Identify consecutive runs in a (date, value) series where the value
    is constant for at least `min_length_days` consecutive entries.

    This is a FACT, not a verdict. Flat runs may be entirely legitimate (a
    bond that doesn't trade, an instrument on holiday, an FX peg). The agent
    interprets the runs in context.

    Schema (per row): FlatRunSegment(start_date, end_date, value, length_days).

    The series must be sorted by date ascending. `tolerance` allows for
    floating-point equality.

    Example:
        ts = [(d1, 1.5), (d2, 1.5), (d3, 1.5), (d4, 1.6)]
        detect_flat_run_in_series(ts, min_length_days=3)
        -> [FlatRunSegment(d1, d3, 1.5, 3)]
    """
    n = len(series)
    if n == 0 or min_length_days < 1:
        return []
    out: list[FlatRunSegment] = []
    run_start = 0
    for i in range(1, n + 1):
        if i == n or abs(series[i][1] - series[run_start][1]) > tolerance:
            length = i - run_start
            if length >= min_length_days:
                out.append(FlatRunSegment(
                    start_date=series[run_start][0],
                    end_date=series[i - 1][0],
                    value=float(series[run_start][1]),
                    length_days=length,
                ))
            run_start = i
    return out


@audit_tool
def compute_nav_move_bps(nav_t: float, nav_t_minus_1: float) -> float:
    """Day-over-day NAV move in basis points.

    Returns (nav_t / nav_t_minus_1 - 1) * 1e4. Raises ValueError if
    nav_t_minus_1 <= 0.

    Example:
        compute_nav_move_bps(101.0, 100.0)  -> 100.0
    """
    if nav_t_minus_1 <= 0:
        raise ValueError(
            f"nav_t_minus_1 must be > 0, got {nav_t_minus_1}"
        )
    return (float(nav_t) / float(nav_t_minus_1) - 1.0) * 1e4
