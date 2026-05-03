"""Unit tests for tools/reference.py."""
from __future__ import annotations

import json
from datetime import date, time

import pytest

from tools._types import Fund, Instrument, ShareClass, TreatyRate, FundCalendar
from tools.reference import (
    get_funds, get_share_classes, get_fund_domicile,
    get_instruments, get_treaty_rate, get_fund_calendar,
)


def _audit_lines(reset_audit_log_per_test):
    text = reset_audit_log_per_test.read_text(encoding="utf-8").strip()
    return [json.loads(l) for l in text.splitlines() if l]


# ---- get_funds ------------------------------------------------------------
def test_get_funds_returns_all_funds(reset_audit_log_per_test):
    funds = get_funds()
    assert len(funds) == 8
    assert all(isinstance(f, Fund) for f in funds)
    ids = {f.fund_id for f in funds}
    assert {"ATLAS", "AURORA", "COBAL", "HELIO", "MERID", "NORDIC", "PACIF", "STERL"} == ids
    # Audit log emitted exactly one row.
    log = _audit_lines(reset_audit_log_per_test)
    assert len(log) == 1
    assert log[0]["tool"] == "reference.get_funds"
    assert log[0]["output"]["row_count"] == 8


def test_get_funds_filtered_one():
    funds = get_funds(fund_id="AURORA")
    assert len(funds) == 1
    f = funds[0]
    assert f.fund_id == "AURORA"
    assert f.base_ccy == "USD"
    assert f.tolerance_bps > 0


def test_get_funds_unknown_id_returns_empty():
    funds = get_funds(fund_id="DOES_NOT_EXIST")
    assert funds == []


# ---- get_share_classes ----------------------------------------------------
def test_get_share_classes_atlas_has_two_classes():
    classes = get_share_classes("ATLAS")
    codes = {c.class_code for c in classes}
    assert codes == {"A", "I"}
    assert all(isinstance(c, ShareClass) for c in classes)
    a = next(c for c in classes if c.class_code == "A")
    assert a.mgmt_fee_bps == 150
    assert a.has_hwm is False


def test_get_share_classes_cobal_has_hwm():
    classes = get_share_classes("COBAL")
    assert all(c.has_hwm for c in classes)
    assert all(c.perf_fee_bps > 0 for c in classes)


def test_get_share_classes_unknown_fund_returns_empty():
    assert get_share_classes("DOES_NOT_EXIST") == []


# ---- get_fund_domicile ----------------------------------------------------
def test_get_fund_domicile_known():
    assert get_fund_domicile("AURORA") == "LU"
    assert get_fund_domicile("ATLAS") == "IE"
    assert get_fund_domicile("COBAL") == "KY"


def test_get_fund_domicile_unknown_returns_none():
    assert get_fund_domicile("DOES_NOT_EXIST") is None


# ---- get_instruments ------------------------------------------------------
def test_get_instruments_no_filter_returns_all():
    instrs = get_instruments()
    assert len(instrs) >= 100  # warehouse ships ~106
    assert all(isinstance(i, Instrument) for i in instrs)


def test_get_instruments_by_id():
    instrs = get_instruments(instrument_id="EQ_EM_SAMSU")
    assert len(instrs) == 1
    s = instrs[0]
    assert s.country == "KR"
    assert s.ccy == "KRW"
    assert s.type == "EQUITY"


def test_get_instruments_by_country():
    kr = get_instruments(country="KR")
    assert len(kr) >= 1
    assert all(i.country == "KR" for i in kr)


def test_get_instruments_unknown_returns_empty():
    assert get_instruments(instrument_id="EQ_DOES_NOT_EXIST") == []


# ---- get_treaty_rate ------------------------------------------------------
def test_get_treaty_rate_lu_kr():
    t = get_treaty_rate("LU", "KR")
    assert isinstance(t, TreatyRate)
    assert t.treaty_rate == pytest.approx(0.15)
    assert t.statutory_rate == pytest.approx(0.22)


def test_get_treaty_rate_missing_pair_returns_none():
    assert get_treaty_rate("LU", "XX") is None


# ---- get_fund_calendar ----------------------------------------------------
def test_get_fund_calendar_atlas_a():
    c = get_fund_calendar("ATLAS", "A")
    assert isinstance(c, FundCalendar)
    assert c.cutoff_local_time == time(12, 0)
    assert c.dealing_days == "BUSINESS_DAYS"


def test_get_fund_calendar_unknown_class_raises():
    with pytest.raises(KeyError):
        get_fund_calendar("ATLAS", "ZZ")
