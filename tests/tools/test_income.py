"""Unit tests for tools/income.py."""
from __future__ import annotations

from datetime import date

from tools._types import CorporateAction, DividendReceipt
from tools.income import get_corporate_actions, get_dividend_receipts


# ---- get_corporate_actions ------------------------------------------------
def test_get_corporate_actions_no_filter_returns_many():
    cas = get_corporate_actions()
    assert len(cas) > 0
    assert all(isinstance(c, CorporateAction) for c in cas)


def test_get_corporate_actions_does_not_expose_applied_flag():
    fields = set(CorporateAction.__dataclass_fields__.keys())
    assert "applied_flag" not in fields


def test_get_corporate_actions_by_instrument():
    cas = get_corporate_actions(instrument_id="EQ_US_AAPL")
    assert all(c.instrument_id == "EQ_US_AAPL" for c in cas)


def test_get_corporate_actions_by_date_range():
    cas = get_corporate_actions(date_range=(date(2026, 4, 1), date(2026, 4, 5)))
    assert all(date(2026, 4, 1) <= c.ex_date <= date(2026, 4, 5) for c in cas)


def test_get_corporate_actions_by_type():
    cas = get_corporate_actions(ca_types=["SPECIAL_DIV"])
    assert all(c.ca_type == "SPECIAL_DIV" for c in cas)


def test_get_corporate_actions_empty_filter():
    cas = get_corporate_actions(instrument_id="EQ_DOES_NOT_EXIST")
    assert cas == []


# ---- get_dividend_receipts -----------------------------------------------
def test_get_dividend_receipts_for_aurora_samsung():
    receipts = get_dividend_receipts(
        fund_id="AURORA", instrument_id="EQ_EM_SAMSU"
    )
    # Defect 9 inserts at least one receipt for this combo.
    assert len(receipts) >= 1
    assert all(isinstance(r, DividendReceipt) for r in receipts)
    assert all(r.fund_id == "AURORA" for r in receipts)


def test_get_dividend_receipts_by_date_range():
    rs = get_dividend_receipts(date_range=(date(2026, 3, 12), date(2026, 3, 12)))
    assert all(r.as_of_date == date(2026, 3, 12) for r in rs)


def test_get_dividend_receipts_unknown_fund_empty():
    assert get_dividend_receipts(fund_id="DOES_NOT_EXIST") == []
