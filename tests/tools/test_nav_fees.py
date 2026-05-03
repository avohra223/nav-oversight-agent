"""Unit tests for tools/nav_fees.py."""
from __future__ import annotations

from datetime import date

import pandas as pd

from tools._types import FeeAccrual
from tools.nav_fees import get_nav_history, get_fee_accruals


# ---- get_nav_history ------------------------------------------------------
def test_get_nav_history_returns_dataframe_without_is_break():
    df = get_nav_history(
        "COBAL", "I", date(2026, 4, 1), date(2026, 4, 30)
    )
    assert isinstance(df, pd.DataFrame)
    expected = {
        "as_of_date", "gav_base", "fees_accrued", "nav_base",
        "shares_outstanding", "nav_per_share", "prior_nav_per_share",
        "nav_move_bps",
    }
    assert set(df.columns) == expected
    # Must not project the ground-truth break flag.
    assert "is_break" not in df.columns
    assert len(df) > 0


def test_get_nav_history_chronological():
    df = get_nav_history(
        "ATLAS", "A", date(2026, 1, 5), date(2026, 1, 31)
    )
    assert df["as_of_date"].is_monotonic_increasing


def test_get_nav_history_empty_range():
    df = get_nav_history(
        "ATLAS", "A", date(2020, 1, 1), date(2020, 1, 5)
    )
    assert len(df) == 0


def test_get_nav_history_unknown_class_empty():
    df = get_nav_history(
        "ATLAS", "ZZ", date(2026, 1, 5), date(2026, 1, 10)
    )
    assert len(df) == 0


# ---- get_fee_accruals -----------------------------------------------------
def test_get_fee_accruals_for_cobal_class_i():
    rows = get_fee_accruals(
        "COBAL", "I", (date(2026, 4, 14), date(2026, 4, 16)),
    )
    assert all(isinstance(r, FeeAccrual) for r in rows)
    assert all(r.fund_id == "COBAL" and r.class_code == "I" for r in rows)


def test_get_fee_accruals_empty_window():
    rows = get_fee_accruals(
        "COBAL", "I", (date(2020, 1, 1), date(2020, 1, 5)),
    )
    assert rows == []


def test_get_fee_accruals_carries_hwm_field():
    """The agent needs hwm_nav_per_share to investigate defect 5."""
    fields = set(FeeAccrual.__dataclass_fields__.keys())
    assert "hwm_nav_per_share" in fields
    assert "perf_fee_balance" in fields
