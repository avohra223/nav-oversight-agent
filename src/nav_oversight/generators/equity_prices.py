"""Equity price generator using a region + sector + idiosyncratic factor model.

Each daily log-return is the sum of:
  - a region factor (per region, per day) -- captures broad market move
  - a sector factor (per sector, per day) -- captures sector rotation
  - an idiosyncratic shock (per instrument, per day)

This produces correlated price paths that look realistic in aggregate while
each instrument retains its own idio noise.
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np

from ..config import (
    MARKET_VOL_ANNUAL, SECTOR_VOL_ANNUAL, IDIO_VOL_ANNUAL,
    TRADING_DAYS_PER_YEAR, RANDOM_SEED,
)
from .reference import ALL_INSTRUMENTS, SECTORS, InstrumentRef


# Region tag derived from country.
def _region_for(country: str) -> str:
    if country in {"US", "CA"}:
        return "NA"
    if country in {"DE", "FR", "NL", "CH", "ES", "GB", "IT", "BE", "AT", "PT", "IE", "LU"}:
        return "EU"
    if country in {"FI", "DK", "SE", "NO"}:
        return "NORDIC"
    if country == "JP":
        return "JP"
    if country in {"TW", "KR", "HK", "IN", "BR", "MX", "ZA", "CN"}:
        return "EM"
    return "OTHER"


REGIONS = ("NA", "EU", "NORDIC", "JP", "EM")


def generate_equity_prices(
    dates: list[date],
) -> list[tuple[date, str, float, str]]:
    """Returns list of (as_of_date, instrument_id, price, source) tuples.

    Two sources are written -- 'PRIMARY' and 'SECONDARY' -- with SECONDARY a
    small noise on PRIMARY (used for cross-source disagreement detection).
    """
    rng = np.random.default_rng(RANDOM_SEED ^ 0xE0)
    n = len(dates)

    daily_market_sigma = MARKET_VOL_ANNUAL / math.sqrt(TRADING_DAYS_PER_YEAR)
    daily_sector_sigma = SECTOR_VOL_ANNUAL / math.sqrt(TRADING_DAYS_PER_YEAR)
    daily_idio_sigma = IDIO_VOL_ANNUAL / math.sqrt(TRADING_DAYS_PER_YEAR)

    # Tiny positive market drift so prices generally trend modestly.
    daily_drift = 0.04 / TRADING_DAYS_PER_YEAR

    # Region returns: one path per region.
    region_returns = {
        r: rng.normal(daily_drift, daily_market_sigma, size=n) for r in REGIONS
    }
    # Add some region-specific tilt: EM and NORDIC are more volatile.
    region_returns["EM"] *= 1.30
    region_returns["NORDIC"] *= 1.10

    sector_returns = {
        s: rng.normal(0.0, daily_sector_sigma, size=n) for s in SECTORS
    }

    equities: tuple[InstrumentRef, ...] = tuple(
        i for i in ALL_INSTRUMENTS if i.type == "EQUITY"
    )

    out: list[tuple[date, str, float, str]] = []
    for instr in equities:
        region = _region_for(instr.country)
        idio = rng.normal(0.0, daily_idio_sigma, size=n)

        log_returns = (
            region_returns[region]
            + 0.7 * sector_returns[instr.sector]
            + idio
        )
        log_prices = np.cumsum(log_returns) + math.log(instr.initial_price)
        prices = np.exp(log_prices)

        # Secondary source: small disagreement (typical vendor-to-vendor noise <10bps).
        secondary_noise = rng.normal(0.0, 0.0008, size=n)
        secondary_prices = prices * np.exp(secondary_noise)

        for i, d in enumerate(dates):
            out.append((d, instr.instrument_id, float(prices[i]), "PRIMARY"))
            out.append((d, instr.instrument_id, float(secondary_prices[i]), "SECONDARY"))

    return out


def write_equity_prices(con, dates: list[date]) -> None:
    rows = generate_equity_prices(dates)
    con.executemany("INSERT INTO prices VALUES (?, ?, ?, ?)", rows)
