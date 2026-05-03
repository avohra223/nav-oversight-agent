"""Unit tests for tools/positions.py."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from tools._types import Holding, Trade, CashBalance, CapstockEvent
from tools.positions import (
    get_holdings, get_holdings_history, get_trades, get_cash, get_capstock,
)


# ---- get_holdings ---------------------------------------------------------
def test_get_holdings_pacif_on_defect_day():
    rows = get_holdings("PACIF", date(2026, 2, 25))
    assert len(rows) > 0
    assert all(isinstance(r, Holding) for r in rows)
    assert all(r.fund_id == "PACIF" for r in rows)
    assert all(r.as_of_date == date(2026, 2, 25) for r in rows)


def test_get_holdings_with_instrument_filter():
    rows = get_holdings("AURORA", date(2026, 3, 12), instrument_id="EQ_EM_SAMSU")
    assert len(rows) == 1
    h = rows[0]
    assert h.instrument_id == "EQ_EM_SAMSU"
    assert h.quantity > 0


def test_get_holdings_empty_for_unknown_fund():
    rows = get_holdings("DOES_NOT_EXIST", date(2026, 2, 25))
    assert rows == []


def test_get_holdings_empty_for_date_outside_window():
    rows = get_holdings("PACIF", date(2020, 1, 1))
    assert rows == []


# ---- get_holdings_history -------------------------------------------------
def test_get_holdings_history_returns_dataframe():
    df = get_holdings_history(
        "NORDIC", "EQ_NS_LITH", date(2026, 2, 5), date(2026, 2, 15)
    )
    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) == {
        "as_of_date", "quantity", "price_local", "ccy",
        "mv_local", "fx_to_base", "mv_base",
    }
    assert len(df) > 0
    assert df["as_of_date"].is_monotonic_increasing


def test_get_holdings_history_empty_range_returns_empty_df():
    df = get_holdings_history(
        "NORDIC", "EQ_NS_LITH", date(2020, 1, 1), date(2020, 1, 5)
    )
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0


# ---- get_trades -----------------------------------------------------------
def test_get_trades_one_day_window():
    rows = get_trades("HELIO", (date(2026, 2, 4), date(2026, 2, 4)))
    assert all(isinstance(r, Trade) for r in rows)
    assert all(r.fund_id == "HELIO" for r in rows)
    assert all(r.trade_date == date(2026, 2, 4) for r in rows)


def test_get_trades_with_instrument_filter():
    rows = get_trades(
        "HELIO", (date(2026, 1, 1), date(2026, 4, 30)),
        instrument_id="EQ_EU_ASML",
    )
    assert all(r.instrument_id == "EQ_EU_ASML" for r in rows)


def test_get_trades_does_not_expose_booking_note():
    """The Trade dataclass must not contain a booking_note field."""
    fields = set(Trade.__dataclass_fields__.keys())
    assert "booking_note" not in fields


def test_get_trades_empty_window():
    assert get_trades("HELIO", (date(2020, 1, 1), date(2020, 1, 5))) == []


# ---- get_cash -------------------------------------------------------------
def test_get_cash_returns_balances():
    rows = get_cash("ATLAS", date(2026, 3, 5))
    assert len(rows) >= 1
    assert all(isinstance(r, CashBalance) for r in rows)
    assert all(r.fund_id == "ATLAS" for r in rows)


def test_get_cash_with_ccy_filter():
    rows = get_cash("ATLAS", date(2026, 3, 5), ccy="USD")
    assert all(r.ccy == "USD" for r in rows)


def test_get_cash_unknown_fund_empty():
    assert get_cash("DOES_NOT_EXIST", date(2026, 3, 5)) == []


# ---- get_capstock ---------------------------------------------------------
def test_get_capstock_atlas_a_defect_day():
    rows = get_capstock("ATLAS", "A", (date(2026, 3, 5), date(2026, 3, 5)))
    assert len(rows) >= 1
    assert all(isinstance(r, CapstockEvent) for r in rows)
    # Tool must expose timestamps so the agent can compare; no flag on validity.
    assert all(isinstance(r.order_received_ts, datetime) for r in rows)
    assert all(isinstance(r.cutoff_ts, datetime) for r in rows)


def test_get_capstock_empty_for_unknown_class():
    assert get_capstock("ATLAS", "ZZ", (date(2026, 3, 5), date(2026, 3, 5))) == []


def test_get_capstock_empty_window():
    assert get_capstock("ATLAS", "A", (date(2020, 1, 1), date(2020, 1, 5))) == []
