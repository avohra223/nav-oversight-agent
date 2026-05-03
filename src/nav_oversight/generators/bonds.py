"""Bond price + accrued-interest generator.

Daily log return of a bond's clean price is approximated as ``-duration * dy``
where ``dy`` is the day's yield change. We build per-currency yield shocks so
bonds in the same ccy move coherently, plus a small per-bond idio.

Accrued interest grows linearly day-over-day using actual/365. We choose each
bond's initial "days since last coupon" so no coupon payment falls inside the
generation window -- this keeps the baseline NAV math simple. Coupon-dated
cash flows are out of scope for v0.
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np

from ..config import RANDOM_SEED, TRADING_DAYS_PER_YEAR
from .reference import ALL_INSTRUMENTS, InstrumentRef


# Modified duration approximation for our 4-9y IG corporates. Real number per
# bond would require yield curve plumbing; this is good enough for synthetic.
DEFAULT_DURATION = 5.5


def generate_bond_data(
    dates: list[date],
) -> tuple[list[tuple[date, str, float, str]], list[tuple[date, str, float]]]:
    """Returns (price_rows, accrual_rows).

    price_rows: (as_of_date, instrument_id, price, source)
    accrual_rows: (as_of_date, instrument_id, accrued_interest_pct)
    """
    rng = np.random.default_rng(RANDOM_SEED ^ 0xB0)
    n = len(dates)

    bonds: tuple[InstrumentRef, ...] = tuple(
        i for i in ALL_INSTRUMENTS if i.type == "BOND"
    )

    # Per-currency yield shock series.
    bond_ccys = sorted({b.ccy for b in bonds})
    daily_rate_sigma = 0.00040    # ~4bps stdev daily yield move
    rate_shocks_by_ccy = {
        ccy: rng.normal(0.0, daily_rate_sigma, size=n) for ccy in bond_ccys
    }
    # Mild mean-reversion of cumulative shock so prices don't drift to absurd levels.
    for ccy in bond_ccys:
        cum = np.cumsum(rate_shocks_by_ccy[ccy])
        rate_shocks_by_ccy[ccy] = rate_shocks_by_ccy[ccy] - 0.02 * cum

    price_rows: list[tuple[date, str, float, str]] = []
    accrual_rows: list[tuple[date, str, float]] = []

    for bond in bonds:
        # Idiosyncratic yield shock (bond-specific spread move).
        idio_dy = rng.normal(0.0, daily_rate_sigma * 0.5, size=n)
        rate_dy = rate_shocks_by_ccy[bond.ccy]
        log_returns = -DEFAULT_DURATION * (rate_dy + idio_dy)
        log_prices = np.cumsum(log_returns) + math.log(bond.initial_price)
        prices = np.exp(log_prices)

        # Secondary source: small disagreement.
        secondary_noise = rng.normal(0.0, 0.0006, size=n)
        secondary = prices * np.exp(secondary_noise)

        # Accrued interest. Pick days_since_last_coupon at start so no pay
        # date falls inside [START, END]. With our window <= 120 days we want:
        #   days_since_start < period_length_days - window_length
        # period_length = 365/coupon_freq. Conservatively, use [5, 60] for any freq.
        days_since_init = int(rng.integers(5, 60))
        daily_accrual_pct = bond.coupon_rate * 100.0 / 365.0

        for i, d in enumerate(dates):
            price_rows.append((d, bond.instrument_id, float(prices[i]), "PRIMARY"))
            price_rows.append((d, bond.instrument_id, float(secondary[i]), "SECONDARY"))
            accrued = (days_since_init + i) * daily_accrual_pct
            accrual_rows.append((d, bond.instrument_id, float(accrued)))

    return price_rows, accrual_rows


def write_bonds(con, dates: list[date]) -> None:
    price_rows, accrual_rows = generate_bond_data(dates)
    con.executemany("INSERT INTO prices VALUES (?, ?, ?, ?)", price_rows)
    con.executemany("INSERT INTO bond_accruals VALUES (?, ?, ?)", accrual_rows)
