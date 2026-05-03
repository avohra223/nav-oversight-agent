"""Market data tools: prices, FX rates, bond accruals."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from ._audit import audit_tool
from ._db import coerce_date_columns, connection
from ._types import FxRate


@audit_tool
def get_price_series(
    instrument_id: str,
    start_date: date,
    end_date: date,
    source: str = "PRIMARY",
) -> pd.DataFrame:
    """Return daily price time series for one instrument.

    Schema (DataFrame columns): as_of_date, price.

    Does NOT detect staleness, gaps, or cross-source disagreement -- query
    both sources separately and compare in the caller.

    Example:
        get_price_series('EQ_NS_LITH', date(2026,2,5), date(2026,2,15))
        get_price_series('EQ_US_AAPL', date(2026,4,1), date(2026,4,5),
                         source='SECONDARY')
    """
    sql = (
        "SELECT as_of_date, price FROM prices "
        "WHERE instrument_id = ? AND source = ? "
        "AND as_of_date BETWEEN ? AND ? "
        "ORDER BY as_of_date"
    )
    df = connection().execute(
        sql, [instrument_id, source, start_date, end_date]
    ).fetch_df()
    return coerce_date_columns(df, ("as_of_date",))


@audit_tool
def get_price_around_date(
    instrument_id: str,
    target_date: date,
    lookback_days: int = 5,
    lookahead_days: int = 1,
    source: str = "PRIMARY",
) -> pd.DataFrame:
    """Return prices in a window centered on a target date.

    Schema (DataFrame columns): as_of_date, price.

    Useful for "what was the price the day before ex-date" patterns. The
    caller picks rows by date.

    Does NOT identify which row is "pre-ex" or compare against a CA -- the
    caller does that.

    Example:
        get_price_around_date('EQ_US_AAPL', date(2026,4,2), lookback_days=3)
    """
    start = target_date - timedelta(days=lookback_days)
    end = target_date + timedelta(days=lookahead_days)
    sql = (
        "SELECT as_of_date, price FROM prices "
        "WHERE instrument_id = ? AND source = ? "
        "AND as_of_date BETWEEN ? AND ? "
        "ORDER BY as_of_date"
    )
    df = connection().execute(
        sql, [instrument_id, source, start, end]
    ).fetch_df()
    return coerce_date_columns(df, ("as_of_date",))


@audit_tool
def get_fx_rate(
    ccy: str, as_of_date: date, snap: str = "LDN_4PM"
) -> FxRate | None:
    """Return one FX rate (USD per unit of `ccy`) for a single date and snap.

    Schema: FxRate(as_of_date, ccy, snap, rate_to_usd). Returns None if no
    row exists for the (ccy, date, snap) combination.

    Does NOT compare across snaps -- use get_fx_rates_all_snaps for that.

    Example:
        get_fx_rate('JPY', date(2026,2,25), 'LDN_4PM')
    """
    sql = (
        "SELECT as_of_date, ccy, snap, rate_to_usd FROM fx_rates "
        "WHERE ccy = ? AND as_of_date = ? AND snap = ?"
    )
    row = connection().execute(sql, [ccy, as_of_date, snap]).fetchone()
    return None if row is None else FxRate(*row)


@audit_tool
def get_fx_rates_all_snaps(ccy: str, as_of_date: date) -> list[FxRate]:
    """Return FX rates for one ccy on one date across all available snaps.

    Schema (per row): FxRate(as_of_date, ccy, snap, rate_to_usd).

    The snaps in v0 are: LDN_4PM, NY_10AM, TKY_3PM, WMR_4PM. The caller can
    diff snap-to-snap to surface intraday FX moves; this tool just returns
    the values.

    Example:
        get_fx_rates_all_snaps('JPY', date(2026,2,25))
    """
    sql = (
        "SELECT as_of_date, ccy, snap, rate_to_usd FROM fx_rates "
        "WHERE ccy = ? AND as_of_date = ? ORDER BY snap"
    )
    rows = connection().execute(sql, [ccy, as_of_date]).fetchall()
    return [FxRate(*r) for r in rows]


@audit_tool
def get_bond_accruals(
    instrument_id: str, start_date: date, end_date: date
) -> pd.DataFrame:
    """Return daily accrued-interest-pct time series for one bond.

    Schema (DataFrame columns): as_of_date, accrued_interest_pct.

    Does NOT detect flat runs or compare against expected accrual; use
    detect_flat_run_in_series and compute_expected_coupon_accrual for that.

    Example:
        get_bond_accruals('BND_GBP_BARC_2031',
                          date(2026,3,15), date(2026,3,30))
    """
    sql = (
        "SELECT as_of_date, accrued_interest_pct FROM bond_accruals "
        "WHERE instrument_id = ? AND as_of_date BETWEEN ? AND ? "
        "ORDER BY as_of_date"
    )
    df = connection().execute(
        sql, [instrument_id, start_date, end_date]
    ).fetch_df()
    return coerce_date_columns(df, ("as_of_date",))
