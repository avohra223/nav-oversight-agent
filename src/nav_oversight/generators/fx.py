"""FX time-series generator.

Each currency vs USD evolves under a mean-reverting Ornstein-Uhlenbeck process
on log-rate. Multiple intraday snaps are produced per day (LDN_4PM is treated
as the canonical 'policy' snap; others differ by a small intraday noise term).
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np

from ..config import (
    FX_VS_USD_INITIAL, FX_VOL, FX_MEAN_REVERSION, FX_SNAPS,
    TRADING_DAYS_PER_YEAR, RANDOM_SEED,
)


def _ou_log_path(
    rng: np.random.Generator,
    initial: float,
    annual_vol: float,
    n_days: int,
    kappa: float,
) -> np.ndarray:
    """Discrete OU on log(rate). Returns array of length n_days starting at log(initial)."""
    dt = 1.0
    daily_sigma = annual_vol / math.sqrt(TRADING_DAYS_PER_YEAR)
    log_lt = math.log(initial)
    path = np.empty(n_days)
    log_x = log_lt
    for i in range(n_days):
        shock = rng.normal(0.0, daily_sigma)
        log_x = log_x + (-kappa * (log_x - log_lt) * dt) + shock
        path[i] = log_x
    return path


def generate_fx_series(dates: list[date]) -> list[tuple[date, str, str, float]]:
    """Returns list of (as_of_date, ccy, snap, rate_to_usd) tuples for all dates and snaps."""
    rng = np.random.default_rng(RANDOM_SEED ^ 0xF1)
    n = len(dates)
    out: list[tuple[date, str, str, float]] = []

    for ccy, initial in FX_VS_USD_INITIAL.items():
        if ccy == "USD":
            for d in dates:
                for snap in FX_SNAPS:
                    out.append((d, "USD", snap, 1.0))
            continue

        annual_vol = FX_VOL[ccy]
        log_path = _ou_log_path(
            rng=rng,
            initial=initial,
            annual_vol=annual_vol,
            n_days=n,
            kappa=FX_MEAN_REVERSION,
        )
        ldn_rates = np.exp(log_path)

        # Intraday noise std: roughly half a daily move.
        intraday_sigma = (annual_vol / math.sqrt(TRADING_DAYS_PER_YEAR)) * 0.45

        # Per-snap deterministic offset (in "fraction of day from LDN_4PM").
        # Used to produce coherent intra-day drift on top of pure noise.
        snap_drift_anchor = {"LDN_4PM": 0.0, "NY_10AM": -0.25, "TKY_3PM": 0.50, "WMR_4PM": 0.05}

        for i, d in enumerate(dates):
            ldn_rate = ldn_rates[i]
            # Daily drift between LDN_4PM and other snaps (idiosyncratic noise + a tiny anchor).
            for snap in FX_SNAPS:
                if snap == "LDN_4PM":
                    out.append((d, ccy, snap, float(ldn_rate)))
                else:
                    drift = snap_drift_anchor[snap] * intraday_sigma * rng.normal(0.0, 1.0) * 0.5
                    noise = rng.normal(0.0, intraday_sigma)
                    rate = ldn_rate * math.exp(noise + drift)
                    out.append((d, ccy, snap, float(rate)))

    return out


def write_fx(con, dates: list[date]) -> None:
    rows = generate_fx_series(dates)
    con.executemany(
        "INSERT INTO fx_rates VALUES (?, ?, ?, ?)", rows,
    )
