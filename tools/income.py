"""Income tools: corporate actions and dividend receipts."""
from __future__ import annotations

from datetime import date

from ._audit import audit_tool
from ._db import connection
from ._types import CorporateAction, DividendReceipt


@audit_tool
def get_corporate_actions(
    instrument_id: str | None = None,
    date_range: tuple[date, date] | None = None,
    ca_types: list[str] | None = None,
) -> list[CorporateAction]:
    """Return corporate actions matching the supplied filters.

    Schema (per row): CorporateAction(ca_id, instrument_id, ca_type, ex_date,
    pay_date, gross_amount, ratio, announced_at).

    Does NOT project applied_flag (a ground-truth field that would leak the
    answer for defect 3). The caller establishes whether a CA was applied by
    checking for a matching dividend_receipt and corroborating with prices.

    Example:
        get_corporate_actions(instrument_id='EQ_US_AAPL')
        get_corporate_actions(date_range=(date(2026,4,1), date(2026,4,30)),
                              ca_types=['CASH_DIV', 'SPECIAL_DIV'])
    """
    sql = (
        "SELECT ca_id, instrument_id, ca_type, ex_date, pay_date, "
        "gross_amount, ratio, announced_at FROM corporate_actions WHERE 1=1"
    )
    params: list = []
    if instrument_id is not None:
        sql += " AND instrument_id = ?"
        params.append(instrument_id)
    if date_range is not None:
        start, end = date_range
        sql += " AND ex_date BETWEEN ? AND ?"
        params.extend([start, end])
    if ca_types is not None and len(ca_types) > 0:
        placeholders = ", ".join(["?"] * len(ca_types))
        sql += f" AND ca_type IN ({placeholders})"
        params.extend(ca_types)
    sql += " ORDER BY ex_date, ca_id"
    rows = connection().execute(sql, params).fetchall()
    return [CorporateAction(*r) for r in rows]


@audit_tool
def get_dividend_receipts(
    fund_id: str | None = None,
    instrument_id: str | None = None,
    date_range: tuple[date, date] | None = None,
) -> list[DividendReceipt]:
    """Return dividend receipt rows matching filters.

    Schema (per row): DividendReceipt(receipt_id, fund_id, instrument_id,
    as_of_date, ccy, gross_amount, wht_rate_used, wht_amount, net_amount).

    Does NOT compare wht_rate_used to a treaty rate -- the caller composes
    this with get_treaty_rate.

    Example:
        get_dividend_receipts(fund_id='AURORA',
                              instrument_id='EQ_EM_SAMSU')
        get_dividend_receipts(date_range=(date(2026,3,1), date(2026,3,31)))
    """
    sql = (
        "SELECT receipt_id, fund_id, instrument_id, as_of_date, ccy, "
        "gross_amount, wht_rate_used, wht_amount, net_amount "
        "FROM dividend_receipts WHERE 1=1"
    )
    params: list = []
    if fund_id is not None:
        sql += " AND fund_id = ?"
        params.append(fund_id)
    if instrument_id is not None:
        sql += " AND instrument_id = ?"
        params.append(instrument_id)
    if date_range is not None:
        start, end = date_range
        sql += " AND as_of_date BETWEEN ? AND ?"
        params.extend([start, end])
    sql += " ORDER BY as_of_date, receipt_id"
    rows = connection().execute(sql, params).fetchall()
    return [DividendReceipt(*r) for r in rows]
