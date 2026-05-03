"""Reference and metadata tools.

Returns funds, share classes, instruments, fund domiciles, treaty rates, and
fund calendars. All tools are facts-only -- no flagging, no thresholding.
"""
from __future__ import annotations

from datetime import date, time

from ._audit import audit_tool
from ._db import connection
from ._types import (
    Fund, ShareClass, Instrument, TreatyRate, FundCalendar,
)


# Fund cutoffs are uniform 12:00 in v0 (matches generators/capstock.py).
_DEFAULT_CUTOFF = time(12, 0)
_DEFAULT_DEALING_DAYS = "BUSINESS_DAYS"


@audit_tool
def get_funds(fund_id: str | None = None) -> list[Fund]:
    """Return fund metadata.

    Schema (per row): Fund(fund_id, name, base_ccy, strategy, tolerance_bps,
    benchmark, inception_date).

    Does NOT: filter by tolerance, flag whether the fund is in breach, or
    project any derived columns.

    Example:
        get_funds()                      # all funds
        get_funds(fund_id='AURORA')      # one fund (list of length 0 or 1)
    """
    sql = (
        "SELECT fund_id, name, base_ccy, strategy, tolerance_bps, benchmark, "
        "inception_date FROM funds"
    )
    params: list = []
    if fund_id is not None:
        sql += " WHERE fund_id = ?"
        params.append(fund_id)
    sql += " ORDER BY fund_id"
    rows = connection().execute(sql, params).fetchall()
    return [Fund(*r) for r in rows]


@audit_tool
def get_share_classes(fund_id: str) -> list[ShareClass]:
    """Return all share classes for a fund.

    Schema (per row): ShareClass(fund_id, class_code, class_name,
    mgmt_fee_bps, perf_fee_bps, has_hwm, initial_nav_per_share,
    initial_shares).

    Does NOT compute current NAV per share or perf fee state -- use
    get_nav_history / get_fee_accruals for that.

    Example:
        get_share_classes('COBAL')       # returns Class I and Class F
    """
    sql = (
        "SELECT fund_id, class_code, class_name, mgmt_fee_bps, perf_fee_bps, "
        "has_hwm, initial_nav_per_share, initial_shares "
        "FROM share_classes WHERE fund_id = ? ORDER BY class_code"
    )
    rows = connection().execute(sql, [fund_id]).fetchall()
    return [ShareClass(*r) for r in rows]


@audit_tool
def get_fund_domicile(fund_id: str) -> str | None:
    """Return the ISO-2 country code where the fund is domiciled.

    Returns None if the fund has no domicile record.

    Example:
        get_fund_domicile('AURORA')  -> 'LU'
    """
    row = connection().execute(
        "SELECT country FROM fund_domiciles WHERE fund_id = ?", [fund_id]
    ).fetchone()
    return None if row is None else str(row[0])


@audit_tool
def get_instruments(
    instrument_id: str | None = None,
    ticker: str | None = None,
    ccy: str | None = None,
    country: str | None = None,
) -> list[Instrument]:
    """Return instrument reference data, filtered by any combination of args.

    Schema (per row): Instrument(instrument_id, ticker, name, type, ccy,
    country, sector, universe_tag, coupon_rate, coupon_freq, maturity_date,
    face_value).

    Does NOT: tell you whether a price is stale, whether a coupon was paid,
    or whether the instrument is held by a fund.

    Example:
        get_instruments(country='KR')          # all Korean instruments
        get_instruments(instrument_id='EQ_EM_SAMSU')  # a single instrument
    """
    sql = (
        "SELECT instrument_id, ticker, name, type, ccy, country, sector, "
        "universe_tag, coupon_rate, coupon_freq, maturity_date, face_value "
        "FROM instruments WHERE 1=1"
    )
    params: list = []
    if instrument_id is not None:
        sql += " AND instrument_id = ?"
        params.append(instrument_id)
    if ticker is not None:
        sql += " AND ticker = ?"
        params.append(ticker)
    if ccy is not None:
        sql += " AND ccy = ?"
        params.append(ccy)
    if country is not None:
        sql += " AND country = ?"
        params.append(country)
    sql += " ORDER BY instrument_id"
    rows = connection().execute(sql, params).fetchall()
    return [Instrument(*r) for r in rows]


@audit_tool
def get_treaty_rate(
    domicile_country: str, source_country: str
) -> TreatyRate | None:
    """Return the WHT treaty + statutory rate for a (domicile, source) pair.

    Schema: TreatyRate(domicile_country, source_country, treaty_rate,
    statutory_rate). Returns None when no entry exists for the pair.

    Does NOT compare against the rate actually used on a dividend receipt;
    the caller does that.

    Example:
        get_treaty_rate('LU', 'KR')  -> TreatyRate(treaty_rate=0.15,
                                                   statutory_rate=0.22, ...)
    """
    row = connection().execute(
        "SELECT domicile_country, source_country, treaty_rate, statutory_rate "
        "FROM wht_treaty WHERE domicile_country = ? AND source_country = ?",
        [domicile_country, source_country],
    ).fetchone()
    return None if row is None else TreatyRate(*row)


@audit_tool
def get_fund_calendar(fund_id: str, share_class: str) -> FundCalendar:
    """Return the dealing calendar for a fund-class.

    Schema: FundCalendar(fund_id, share_class, cutoff_local_time,
    dealing_days). v0 has uniform cutoff 12:00 and BUSINESS_DAYS dealing.

    Raises KeyError if the (fund_id, share_class) does not exist.

    Example:
        get_fund_calendar('ATLAS', 'A')  -> cutoff_local_time=time(12,0)
    """
    row = connection().execute(
        "SELECT 1 FROM share_classes WHERE fund_id = ? AND class_code = ?",
        [fund_id, share_class],
    ).fetchone()
    if row is None:
        raise KeyError(f"share class not found: {fund_id}/{share_class}")
    return FundCalendar(
        fund_id=fund_id,
        share_class=share_class,
        cutoff_local_time=_DEFAULT_CUTOFF,
        dealing_days=_DEFAULT_DEALING_DAYS,
    )
