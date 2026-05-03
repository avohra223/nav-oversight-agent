"""Unit tests for tools/computation.py."""
from __future__ import annotations

from datetime import date

import pytest

from tools._types import AttributionLine, FlatRunSegment, Holding
from tools.computation import (
    compute_implied_dividend_return,
    compute_implied_wht_rate,
    compute_expected_coupon_accrual,
    compute_perf_fee,
    compute_attribution,
    detect_flat_run_in_series,
    compute_nav_move_bps,
)


# ---- compute_implied_dividend_return -------------------------------------
def test_implied_dividend_return_basic():
    assert compute_implied_dividend_return(2.50, 200.0) == pytest.approx(-0.0125)


def test_implied_dividend_return_zero_dividend():
    assert compute_implied_dividend_return(0.0, 100.0) == 0.0


def test_implied_dividend_return_invalid_price():
    with pytest.raises(ValueError):
        compute_implied_dividend_return(2.5, 0.0)
    with pytest.raises(ValueError):
        compute_implied_dividend_return(2.5, -1.0)


# ---- compute_implied_wht_rate --------------------------------------------
def test_implied_wht_rate_basic():
    assert compute_implied_wht_rate(1000.0, 220.0) == pytest.approx(0.22)


def test_implied_wht_rate_zero_gross_raises():
    with pytest.raises(ValueError):
        compute_implied_wht_rate(0.0, 100.0)


# ---- compute_expected_coupon_accrual --------------------------------------
def test_expected_coupon_accrual_act_365():
    # 100 face * 5.5% rate * 4/365 = 0.0603...
    assert compute_expected_coupon_accrual(100.0, 0.055, "ACT/365", 4) == pytest.approx(
        100.0 * 0.055 * 4 / 365.0
    )


def test_expected_coupon_accrual_act_360():
    assert compute_expected_coupon_accrual(100.0, 0.05, "ACT/360", 30) == pytest.approx(
        100.0 * 0.05 * 30 / 360.0
    )


def test_expected_coupon_accrual_unknown_convention_raises():
    with pytest.raises(ValueError):
        compute_expected_coupon_accrual(100.0, 0.05, "MADE_UP", 30)


# ---- compute_perf_fee -----------------------------------------------------
def test_perf_fee_no_hurdle_above_hwm():
    # 20% of (110 - 100) = 2.0
    assert compute_perf_fee(110.0, 100.0, 0, 2000, 365) == pytest.approx(2.0)


def test_perf_fee_below_hwm_returns_zero():
    assert compute_perf_fee(95.0, 100.0, 0, 2000, 365) == 0.0


def test_perf_fee_with_hurdle():
    # hurdle 500bps annualized over 365d -> 5%, so adjusted hwm = 105
    # profit = 110 - 105 = 5; fee = 5 * 0.20 = 1.0
    assert compute_perf_fee(110.0, 100.0, 500, 2000, 365) == pytest.approx(1.0)


def test_perf_fee_negative_perf_rate_raises():
    with pytest.raises(ValueError):
        compute_perf_fee(110.0, 100.0, 0, -100, 365)


# ---- compute_attribution -------------------------------------------------
def _h(instr: str, qty: float) -> Holding:
    return Holding(
        as_of_date=date(2026, 1, 1), fund_id="X", instrument_id=instr,
        quantity=qty, price_local=1.0, ccy="USD",
        mv_local=qty, fx_to_base=1.0, mv_base=qty,
    )


def test_attribution_simple():
    h_t = [_h("A", 100.0), _h("B", 50.0)]
    h_t1 = [_h("A", 100.0), _h("B", 50.0)]
    p_t = {"A": 11.0, "B": 20.0}
    p_t1 = {"A": 10.0, "B": 20.0}
    out = compute_attribution(h_t, h_t1, p_t, p_t1)
    by_id = {a.instrument_id: a for a in out}
    assert by_id["A"].contribution_local == pytest.approx(100.0 * (11.0 - 10.0))
    assert by_id["B"].contribution_local == pytest.approx(0.0)


def test_attribution_position_opened_today_contributes_nothing():
    h_t = [_h("A", 100.0)]   # newly opened
    h_t1: list[Holding] = []
    p_t = {"A": 11.0}
    p_t1 = {"A": 10.0}
    out = compute_attribution(h_t, h_t1, p_t, p_t1)
    assert out[0].instrument_id == "A"
    assert out[0].contribution_local == 0.0  # qty_t-1 == 0


def test_attribution_empty_inputs():
    assert compute_attribution([], [], {}, {}) == []


# ---- detect_flat_run_in_series -------------------------------------------
def test_detect_flat_run_finds_three_day_run():
    series = [
        (date(2026, 2, 6),  100.0),
        (date(2026, 2, 9),  100.0),
        (date(2026, 2, 10), 100.0),
        (date(2026, 2, 11), 100.0),
        (date(2026, 2, 12), 70.0),
    ]
    runs = detect_flat_run_in_series(series, min_length_days=3)
    assert len(runs) == 1
    r = runs[0]
    assert isinstance(r, FlatRunSegment)
    assert r.value == pytest.approx(100.0)
    assert r.length_days == 4
    assert r.start_date == date(2026, 2, 6)
    assert r.end_date == date(2026, 2, 11)


def test_detect_flat_run_no_runs_meeting_min():
    series = [(date(2026, 1, 1), 1.0), (date(2026, 1, 2), 2.0)]
    assert detect_flat_run_in_series(series, min_length_days=3) == []


def test_detect_flat_run_constant_series():
    series = [(date(2026, 1, i + 1), 5.0) for i in range(10)]
    runs = detect_flat_run_in_series(series, min_length_days=3)
    assert len(runs) == 1
    assert runs[0].length_days == 10


def test_detect_flat_run_empty_series():
    assert detect_flat_run_in_series([], min_length_days=3) == []


# ---- compute_nav_move_bps ------------------------------------------------
def test_nav_move_bps_basic():
    assert compute_nav_move_bps(101.0, 100.0) == pytest.approx(100.0)
    assert compute_nav_move_bps(99.5, 100.0) == pytest.approx(-50.0)


def test_nav_move_bps_invalid_prior():
    with pytest.raises(ValueError):
        compute_nav_move_bps(101.0, 0.0)
