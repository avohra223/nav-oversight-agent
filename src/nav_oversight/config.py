"""Central configuration: fund universe, time window, defect schedule.

All synthetic. No real-world fund / portfolio data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "nav.duckdb"

RANDOM_SEED = 20260101

START_DATE = date(2026, 1, 5)
END_DATE = date(2026, 4, 30)


@dataclass(frozen=True)
class ShareClass:
    code: str
    name: str
    mgmt_fee_bps: int
    perf_fee_bps: int = 0
    has_hwm: bool = False
    initial_nav_per_share: float = 100.0
    initial_shares: float = 1_000_000.0


@dataclass(frozen=True)
class Fund:
    fund_id: str
    name: str
    base_ccy: str
    strategy: str
    tolerance_bps: int
    benchmark: str
    classes: tuple[ShareClass, ...]
    target_universe: tuple[str, ...]
    target_n_holdings: int


FUNDS: tuple[Fund, ...] = (
    Fund(
        fund_id="ATLAS",
        name="Atlas Global Equity Fund",
        base_ccy="USD",
        strategy="global_equity",
        tolerance_bps=80,
        benchmark="MSCI World",
        classes=(
            ShareClass("A", "Class A (Retail)", mgmt_fee_bps=150),
            ShareClass("I", "Class I (Institutional)", mgmt_fee_bps=60,
                       initial_nav_per_share=1000.0, initial_shares=200_000.0),
        ),
        target_universe=("US_LARGE", "EU_LARGE", "JP_LARGE"),
        target_n_holdings=45,
    ),
    Fund(
        fund_id="MERID",
        name="Meridian Euro Equity Fund",
        base_ccy="EUR",
        strategy="europe_equity",
        tolerance_bps=130,
        benchmark="MSCI Europe",
        classes=(ShareClass("I", "Class I", mgmt_fee_bps=75),),
        target_universe=("EU_LARGE",),
        target_n_holdings=35,
    ),
    Fund(
        fund_id="PACIF",
        name="Pacific Japan Alpha Fund",
        base_ccy="USD",
        strategy="japan_equity",
        tolerance_bps=200,
        benchmark="TOPIX",
        classes=(ShareClass("I", "Class I", mgmt_fee_bps=85),),
        target_universe=("JP_LARGE",),
        target_n_holdings=25,
    ),
    Fund(
        fund_id="STERL",
        name="Sterling Investment Grade Bond Fund",
        base_ccy="GBP",
        strategy="ig_bond",
        tolerance_bps=125,
        benchmark="ICE BofA Sterling Corporate",
        classes=(ShareClass("I", "Class I", mgmt_fee_bps=40),),
        target_universe=("IG_BOND",),
        target_n_holdings=30,
    ),
    Fund(
        fund_id="HELIO",
        name="Helios Multi-Asset Fund",
        base_ccy="USD",
        strategy="multi_asset",
        tolerance_bps=75,
        benchmark="60/40 Blend",
        classes=(ShareClass("I", "Class I", mgmt_fee_bps=70),),
        target_universe=("US_LARGE", "EU_LARGE", "IG_BOND"),
        target_n_holdings=40,
    ),
    Fund(
        fund_id="COBAL",
        name="Cobalt Long/Short Equity Fund",
        base_ccy="USD",
        strategy="long_short_equity",
        tolerance_bps=100,
        benchmark="HFRI Equity Hedge",
        classes=(
            ShareClass("I", "Class I", mgmt_fee_bps=150, perf_fee_bps=2000, has_hwm=True),
            ShareClass("F", "Founder Class", mgmt_fee_bps=100, perf_fee_bps=1500, has_hwm=True,
                       initial_nav_per_share=1000.0, initial_shares=100_000.0),
        ),
        target_universe=("US_LARGE",),
        target_n_holdings=30,
    ),
    Fund(
        fund_id="AURORA",
        name="Aurora Emerging Markets Fund",
        base_ccy="USD",
        strategy="em_equity",
        tolerance_bps=175,
        benchmark="MSCI EM",
        classes=(ShareClass("I", "Class I", mgmt_fee_bps=110),),
        target_universe=("EM_EQUITY",),
        target_n_holdings=35,
    ),
    Fund(
        fund_id="NORDIC",
        name="Nordic Small Cap Fund",
        base_ccy="EUR",
        strategy="nordic_small_cap",
        tolerance_bps=160,
        benchmark="MSCI Nordic Small Cap",
        classes=(ShareClass("I", "Class I", mgmt_fee_bps=120),),
        target_universe=("NORDIC_SMALL",),
        target_n_holdings=25,
    ),
)


# Defect schedule. Each entry: (defect_id, fund_id, date, share_class_or_None, params).
# The date is the AS-OF date the defect manifests in NAV. Some defects are seeded
# on prior days (e.g. stale price builds up over multiple days) but the break shows
# up here.
@dataclass(frozen=True)
class DefectSpec:
    defect_id: int
    code: str
    fund_id: str
    as_of: date
    share_class: str | None
    params: dict = field(default_factory=dict)


DEFECT_SCHEDULE: tuple[DefectSpec, ...] = (
    DefectSpec(1,  "single_stock_shock",     "MERID",  date(2026, 1, 22), None,
               params={"shock_pct": -0.30, "instrument_id": "EQ_EU_NESN"}),
    DefectSpec(6,  "trade_wrong_side",       "HELIO",  date(2026, 2,  4), None,
               params={"flip_one_trade": True}),
    DefectSpec(4,  "stale_price",            "NORDIC", date(2026, 2, 12), None,
               params={"stale_days": 3, "true_drift_pct": -0.30}),
    DefectSpec(2,  "fx_cutoff_mismatch",     "PACIF",  date(2026, 2, 25), None,
               params={"used_snap": "NY_10AM", "policy_snap": "LDN_4PM",
                       "jpy_intraday_move_pct": 0.025}),
    DefectSpec(8,  "subscription_pre_cutoff","ATLAS",  date(2026, 3,  5), "A",
               params={"sub_amount_usd": 50_000_000, "actual_arrival": "13:30",
                       "stamped_arrival": "11:45", "intraday_market_pct": 0.008}),
    DefectSpec(9,  "wrong_wht",              "AURORA", date(2026, 3, 12), None,
               params={"treaty_rate": 0.15, "applied_rate": 0.22,
                       "issuer_country": "KR"}),
    DefectSpec(7,  "missed_coupon_accrual",  "STERL",  date(2026, 3, 24), None,
               params={"missed_days": 4}),
    DefectSpec(3,  "missed_corp_action",     "HELIO",  date(2026, 4,  2), None,
               params={"ca_type": "SPECIAL_DIV", "div_pct": 0.15,
                       "instrument_id": "EQ_US_AAPL"}),
    DefectSpec(5,  "stale_hwm_perf_fee",     "COBAL",  date(2026, 4, 15), "I",
               params={"true_hwm_offset_pct": 0.025, "stale_hwm_offset_pct": -0.10}),
    DefectSpec(10, "class_fee_misallocation","ATLAS",  date(2026, 4, 23), "I",
               params={"misallocated_from": "A"}),
)


# Where defect days land per fund (used during build to gate certain mutations).
DEFECT_DAYS_BY_FUND: dict[str, list[date]] = {}
for _d in DEFECT_SCHEDULE:
    DEFECT_DAYS_BY_FUND.setdefault(_d.fund_id, []).append(_d.as_of)


# Instruments that must be in a given fund's portfolio at a meaningful weight,
# because a defect targets them. Enforced by portfolio_init.
DEFECT_REQUIRED_HOLDINGS: dict[str, tuple[str, ...]] = {
    "MERID":  ("EQ_EU_NESN",),         # defect 1: -9.2% shock on a 5% position
    "STERL":  ("BND_GBP_BARC_2031",),  # defect 7: missed coupon accrual
    "HELIO":  ("EQ_US_AAPL",),         # defect 3: missed CA on AAPL
    "AURORA": ("EQ_EM_SAMSU",),        # defect 9: wrong WHT on Samsung div
    "NORDIC": ("EQ_NS_LITH",),         # defect 4: stale price
}
REQUIRED_INSTRUMENT_RESERVED_WEIGHT = 0.070  # ~7% per required instrument


# FX universe.
BASE_CCYS = ("USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD",
             "TWD", "KRW", "HKD", "INR", "BRL", "MXN", "ZAR", "SEK", "DKK", "NOK")
FX_VS_USD_INITIAL = {
    "USD": 1.0,
    "EUR": 1.0850,
    "GBP": 1.2700,
    "JPY": 0.00665,    # USD per JPY
    "CHF": 1.1300,
    "CAD": 0.7300,
    "AUD": 0.6600,
    "TWD": 0.0312,
    "KRW": 0.000730,
    "HKD": 0.1280,
    "INR": 0.01195,
    "BRL": 0.2010,
    "MXN": 0.0580,
    "ZAR": 0.0540,
    "SEK": 0.0945,
    "DKK": 0.1455,
    "NOK": 0.0915,
}
# Annualized vol per ccy (vs USD). G10 ~7-10%, EM higher.
FX_VOL = {
    "EUR": 0.075, "GBP": 0.085, "JPY": 0.090, "CHF": 0.080,
    "CAD": 0.075, "AUD": 0.095, "SEK": 0.090, "DKK": 0.075, "NOK": 0.105,
    "TWD": 0.060, "KRW": 0.110, "HKD": 0.020, "INR": 0.070,
    "BRL": 0.180, "MXN": 0.140, "ZAR": 0.170,
}
# Mean-reversion strength toward initial level.
FX_MEAN_REVERSION = 0.015


# Multiple FX snap times (relevant for defect 2).
FX_SNAPS = ("LDN_4PM", "NY_10AM", "TKY_3PM", "WMR_4PM")


# Equity factor model parameters. Held lower than realized broad-market vol
# so baseline NAV noise sits comfortably inside per-fund tolerances; defects
# are then sized to clearly clear tolerance and stand out as investigatable
# breaks.
MARKET_VOL_ANNUAL = 0.05
SECTOR_VOL_ANNUAL = 0.03
IDIO_VOL_ANNUAL = 0.07
TRADING_DAYS_PER_YEAR = 252


# Tolerance break detection — used for verification at the end of the build.
def tolerance_for_strategy(strategy: str) -> int:
    """Fallback tolerance lookup; per-fund tolerance is in `Fund.tolerance_bps`."""
    return {
        "global_equity": 50, "europe_equity": 50, "japan_equity": 60,
        "ig_bond": 25, "multi_asset": 40, "long_short_equity": 100,
        "em_equity": 80, "nordic_small_cap": 75,
    }.get(strategy, 50)
