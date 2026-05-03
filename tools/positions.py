"""Position and transaction tools.

Returns holdings, holdings history, trades, cash balances, and capstock
events. Facts only -- no recon, no flagging, no integrity checks.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from ._audit import audit_tool
from ._db import coerce_date_columns, connection
from ._types import Holding, Trade, CashBalance, CapstockEvent


@audit_tool
def get_holdings(
    fund_id: str, as_of_date: date, instrument_id: str | None = None
) -> list[Holding]:
    """Return holdings for a fund on a single date.

    Schema (per row): Holding(as_of_date, fund_id, instrument_id, quantity,
    price_local, ccy, mv_local, fx_to_base, mv_base).

    Does NOT compare today's holdings to yesterday's, run attribution, or
    check that mv_base * shares_outstanding sums anywhere. Pure read.

    Example:
        get_holdings('PACIF', date(2026,2,25))                  # all PACIF holdings
        get_holdings('AURORA', date(2026,3,12), 'EQ_EM_SAMSU')  # one instrument
    """
    sql = (
        "SELECT as_of_date, fund_id, instrument_id, quantity, price_local, "
        "ccy, mv_local, fx_to_base, mv_base "
        "FROM holdings WHERE fund_id = ? AND as_of_date = ?"
    )
    params: list = [fund_id, as_of_date]
    if instrument_id is not None:
        sql += " AND instrument_id = ?"
        params.append(instrument_id)
    sql += " ORDER BY instrument_id"
    rows = connection().execute(sql, params).fetchall()
    return [Holding(*r) for r in rows]


@audit_tool
def get_holdings_history(
    fund_id: str, instrument_id: str, start_date: date, end_date: date
) -> pd.DataFrame:
    """Return time series of one position in one fund.

    Schema (DataFrame columns): as_of_date, quantity, price_local, ccy,
    mv_local, fx_to_base, mv_base.

    Does NOT identify gaps, anomalies, or stale prices in the series.

    Example:
        get_holdings_history('NORDIC', 'EQ_NS_LITH',
                             date(2026,2,5), date(2026,2,15))
    """
    sql = (
        "SELECT as_of_date, quantity, price_local, ccy, mv_local, fx_to_base, "
        "mv_base FROM holdings "
        "WHERE fund_id = ? AND instrument_id = ? "
        "AND as_of_date BETWEEN ? AND ? "
        "ORDER BY as_of_date"
    )
    df = connection().execute(
        sql, [fund_id, instrument_id, start_date, end_date]
    ).fetch_df()
    return coerce_date_columns(df, ("as_of_date",))


@audit_tool
def get_trades(
    fund_id: str,
    date_range: tuple[date, date],
    instrument_id: str | None = None,
) -> list[Trade]:
    """Return trades for a fund within a date range.

    Schema (per row): Trade(trade_id, fund_id, instrument_id, side, quantity,
    price, ccy, trade_date, settle_date, broker).

    Does NOT project booking_note (a ground-truth field that would leak the
    answer for defect 6).

    Example:
        get_trades('HELIO', (date(2026,2,4), date(2026,2,4)))   # one day
        get_trades('STERL', (date(2026,3,1), date(2026,3,31)))  # one month
    """
    start, end = date_range
    sql = (
        "SELECT trade_id, fund_id, instrument_id, side, quantity, price, ccy, "
        "trade_date, settle_date, broker "
        "FROM trades WHERE fund_id = ? AND trade_date BETWEEN ? AND ?"
    )
    params: list = [fund_id, start, end]
    if instrument_id is not None:
        sql += " AND instrument_id = ?"
        params.append(instrument_id)
    sql += " ORDER BY trade_date, trade_id"
    rows = connection().execute(sql, params).fetchall()
    return [Trade(*r) for r in rows]


@audit_tool
def get_cash(
    fund_id: str, as_of_date: date, ccy: str | None = None
) -> list[CashBalance]:
    """Return cash balances for a fund on a single date.

    Schema (per row): CashBalance(as_of_date, fund_id, ccy, balance).

    Does NOT compare cash to expected dividend receipts or trade settlements.

    Example:
        get_cash('AURORA', date(2026,3,12))
    """
    sql = (
        "SELECT as_of_date, fund_id, ccy, balance "
        "FROM cash WHERE fund_id = ? AND as_of_date = ?"
    )
    params: list = [fund_id, as_of_date]
    if ccy is not None:
        sql += " AND ccy = ?"
        params.append(ccy)
    sql += " ORDER BY ccy"
    rows = connection().execute(sql, params).fetchall()
    return [CashBalance(*r) for r in rows]


@audit_tool
def get_capstock(
    fund_id: str, share_class: str, date_range: tuple[date, date]
) -> list[CapstockEvent]:
    """Return capstock events (subs/reds) for a fund-class within a range.

    Schema (per row): CapstockEvent(capstock_id, fund_id, class_code,
    as_of_date, order_received_ts, cutoff_ts, booked_for_date, flow_type,
    gross_amount_base, shares_delta).

    Does NOT determine whether order_received_ts > cutoff_ts; the caller
    inspects timestamps to draw that conclusion.

    Example:
        get_capstock('ATLAS', 'A', (date(2026,3,5), date(2026,3,5)))
    """
    start, end = date_range
    sql = (
        "SELECT capstock_id, fund_id, class_code, as_of_date, "
        "order_received_ts, cutoff_ts, booked_for_date, flow_type, "
        "gross_amount_base, shares_delta "
        "FROM capstock "
        "WHERE fund_id = ? AND class_code = ? AND as_of_date BETWEEN ? AND ? "
        "ORDER BY as_of_date, capstock_id"
    )
    rows = connection().execute(
        sql, [fund_id, share_class, start, end]
    ).fetchall()
    return [CapstockEvent(*r) for r in rows]
