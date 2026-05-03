"""NAV history and fee accruals."""
from __future__ import annotations

from datetime import date

import pandas as pd

from ._audit import audit_tool
from ._db import coerce_date_columns, connection
from ._types import FeeAccrual


@audit_tool
def get_nav_history(
    fund_id: str, share_class: str, start_date: date, end_date: date
) -> pd.DataFrame:
    """Return daily NAV time series for one share class.

    Schema (DataFrame columns): as_of_date, gav_base, fees_accrued, nav_base,
    shares_outstanding, nav_per_share, prior_nav_per_share, nav_move_bps.

    Does NOT project is_break (a derived flag that would leak which fund-days
    were flagged by the warehouse's own threshold). The caller computes its
    own break determination from nav_move_bps and the fund's tolerance_bps.

    Example:
        get_nav_history('COBAL', 'I', date(2026,4,1), date(2026,4,30))
    """
    sql = (
        "SELECT as_of_date, gav_base, fees_accrued, nav_base, "
        "shares_outstanding, nav_per_share, prior_nav_per_share, nav_move_bps "
        "FROM nav "
        "WHERE fund_id = ? AND class_code = ? "
        "AND as_of_date BETWEEN ? AND ? "
        "ORDER BY as_of_date"
    )
    df = connection().execute(
        sql, [fund_id, share_class, start_date, end_date]
    ).fetch_df()
    return coerce_date_columns(df, ("as_of_date",))


@audit_tool
def get_fee_accruals(
    fund_id: str, share_class: str, date_range: tuple[date, date]
) -> list[FeeAccrual]:
    """Return daily fee accrual rows for one share class.

    Schema (per row): FeeAccrual(as_of_date, fund_id, class_code,
    mgmt_fee_daily, perf_fee_delta, perf_fee_balance, hwm_nav_per_share).

    Does NOT compute expected mgmt fee from AUM or assert the HWM is correct;
    the caller composes with get_share_classes (for fee terms) and
    get_nav_history (for AUM history).

    Example:
        get_fee_accruals('COBAL', 'I',
                        (date(2026,4,1), date(2026,4,30)))
    """
    start, end = date_range
    sql = (
        "SELECT as_of_date, fund_id, class_code, mgmt_fee_daily, "
        "perf_fee_delta, perf_fee_balance, hwm_nav_per_share "
        "FROM fee_accruals "
        "WHERE fund_id = ? AND class_code = ? AND as_of_date BETWEEN ? AND ? "
        "ORDER BY as_of_date"
    )
    rows = connection().execute(
        sql, [fund_id, share_class, start, end]
    ).fetchall()
    return [FeeAccrual(*r) for r in rows]
