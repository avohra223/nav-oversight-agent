"""Unit tests for tools/market_data.py."""
from __future__ import annotations

from datetime import date

import pandas as pd

from tools._types import FxRate
from tools.market_data import (
    get_price_series, get_price_around_date,
    get_fx_rate, get_fx_rates_all_snaps, get_bond_accruals,
)


# ---- get_price_series -----------------------------------------------------
def test_get_price_series_monotonic():
    df = get_price_series(
        "EQ_NS_LITH", date(2026, 2, 5), date(2026, 2, 15)
    )
    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) == {"as_of_date", "price"}
    assert df["as_of_date"].is_monotonic_increasing
    assert (df["price"] > 0).all()


def test_get_price_series_secondary_source_differs_from_primary():
    p = get_price_series("EQ_US_AAPL", date(2026, 1, 5), date(2026, 1, 9), "PRIMARY")
    s = get_price_series("EQ_US_AAPL", date(2026, 1, 5), date(2026, 1, 9), "SECONDARY")
    # Same dates, but values are noisy versions of each other.
    merged = p.merge(s, on="as_of_date", suffixes=("_p", "_s"))
    diffs = (merged["price_p"] - merged["price_s"]).abs()
    assert (diffs > 0).any()


def test_get_price_series_empty_range():
    df = get_price_series("EQ_US_AAPL", date(2020, 1, 1), date(2020, 1, 5))
    assert len(df) == 0


# ---- get_price_around_date -----------------------------------------------
def test_get_price_around_date_window():
    df = get_price_around_date(
        "EQ_US_AAPL", date(2026, 4, 2), lookback_days=3, lookahead_days=1,
    )
    assert isinstance(df, pd.DataFrame)
    assert len(df) >= 2
    assert df["as_of_date"].min() <= date(2026, 4, 2)
    assert df["as_of_date"].max() >= date(2026, 4, 2)


def test_get_price_around_date_unknown_instrument_empty():
    df = get_price_around_date("EQ_DOES_NOT_EXIST", date(2026, 4, 2))
    assert len(df) == 0


# ---- get_fx_rate ----------------------------------------------------------
def test_get_fx_rate_jpy_ldn_4pm():
    fx = get_fx_rate("JPY", date(2026, 2, 25), "LDN_4PM")
    assert isinstance(fx, FxRate)
    assert fx.snap == "LDN_4PM"
    assert fx.ccy == "JPY"
    assert 0 < fx.rate_to_usd < 1.0  # USD per JPY is small


def test_get_fx_rate_unknown_returns_none():
    assert get_fx_rate("XYZ", date(2026, 2, 25)) is None


# ---- get_fx_rates_all_snaps -----------------------------------------------
def test_get_fx_rates_all_snaps_returns_four_snaps():
    rates = get_fx_rates_all_snaps("JPY", date(2026, 2, 25))
    snaps = {r.snap for r in rates}
    assert snaps == {"LDN_4PM", "NY_10AM", "TKY_3PM", "WMR_4PM"}


def test_get_fx_rates_all_snaps_empty_for_unknown():
    assert get_fx_rates_all_snaps("XYZ", date(2026, 2, 25)) == []


# ---- get_bond_accruals ----------------------------------------------------
def test_get_bond_accruals_monotonic_under_normal_conditions():
    df = get_bond_accruals(
        "BND_USD_AAPL_2031", date(2026, 1, 5), date(2026, 1, 31),
    )
    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) == {"as_of_date", "accrued_interest_pct"}
    # Bond should accrue normally; no flat-run injection on this one.
    assert df["accrued_interest_pct"].is_monotonic_increasing


def test_get_bond_accruals_empty_for_unknown():
    df = get_bond_accruals("BND_DOES_NOT_EXIST", date(2026, 1, 5), date(2026, 1, 10))
    assert len(df) == 0
