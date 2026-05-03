"""Shared dataclasses returned by the tool layer.

All tool outputs that aren't pandas DataFrames are typed dataclasses defined
here. This file does NOT import duckdb or any DB module -- it's pure types so
the agent can reason about tool signatures without DB plumbing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time


@dataclass(frozen=True)
class Fund:
    fund_id: str
    name: str
    base_ccy: str
    strategy: str
    tolerance_bps: int
    benchmark: str
    inception_date: date


@dataclass(frozen=True)
class ShareClass:
    fund_id: str
    class_code: str
    class_name: str
    mgmt_fee_bps: int
    perf_fee_bps: int
    has_hwm: bool
    initial_nav_per_share: float
    initial_shares: float


@dataclass(frozen=True)
class Instrument:
    instrument_id: str
    ticker: str
    name: str
    type: str
    ccy: str
    country: str
    sector: str | None
    universe_tag: str
    coupon_rate: float | None
    coupon_freq: int | None
    maturity_date: date | None
    face_value: float | None


@dataclass(frozen=True)
class TreatyRate:
    domicile_country: str
    source_country: str
    treaty_rate: float
    statutory_rate: float


@dataclass(frozen=True)
class FundCalendar:
    fund_id: str
    share_class: str
    cutoff_local_time: time
    dealing_days: str  # "BUSINESS_DAYS" in v0


@dataclass(frozen=True)
class Holding:
    as_of_date: date
    fund_id: str
    instrument_id: str
    quantity: float
    price_local: float
    ccy: str
    mv_local: float
    fx_to_base: float
    mv_base: float


@dataclass(frozen=True)
class Trade:
    trade_id: str
    fund_id: str
    instrument_id: str
    side: str
    quantity: float
    price: float
    ccy: str
    trade_date: date
    settle_date: date
    broker: str | None


@dataclass(frozen=True)
class CashBalance:
    as_of_date: date
    fund_id: str
    ccy: str
    balance: float


@dataclass(frozen=True)
class CapstockEvent:
    capstock_id: str
    fund_id: str
    class_code: str
    as_of_date: date
    order_received_ts: datetime
    cutoff_ts: datetime
    booked_for_date: date
    flow_type: str
    gross_amount_base: float
    shares_delta: float


@dataclass(frozen=True)
class FxRate:
    as_of_date: date
    ccy: str
    snap: str
    rate_to_usd: float


@dataclass(frozen=True)
class CorporateAction:
    ca_id: str
    instrument_id: str
    ca_type: str
    ex_date: date
    pay_date: date
    gross_amount: float | None
    ratio: float | None
    announced_at: date


@dataclass(frozen=True)
class DividendReceipt:
    receipt_id: str
    fund_id: str
    instrument_id: str
    as_of_date: date
    ccy: str
    gross_amount: float
    wht_rate_used: float
    wht_amount: float
    net_amount: float


@dataclass(frozen=True)
class FeeAccrual:
    as_of_date: date
    fund_id: str
    class_code: str
    mgmt_fee_daily: float
    perf_fee_delta: float
    perf_fee_balance: float
    hwm_nav_per_share: float | None


@dataclass(frozen=True)
class AttributionLine:
    instrument_id: str
    qty_t_minus_1: float
    price_t_minus_1: float
    price_t: float
    contribution_local: float


@dataclass(frozen=True)
class FlatRunSegment:
    start_date: date
    end_date: date
    value: float
    length_days: int
