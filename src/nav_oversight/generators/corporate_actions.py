"""Corporate actions schedule.

Baseline: each equity gets 0-2 cash dividends scattered across the window with
applied_flag=True (cash receipt is implicitly booked elsewhere). Bonds get no
CAs in v0 -- coupon mechanics are handled via accrued interest.

Defect 3 (missed corporate action) is injected later by the defect module,
which writes a CA record with applied_flag=False and adjusts the price on the
ex-date so the agent has a real signal to pick up.
"""
from __future__ import annotations

from datetime import date

import numpy as np

from ..config import RANDOM_SEED
from .reference import ALL_INSTRUMENTS, InstrumentRef


# Per-region typical annual dividend yield ranges and frequency (events per year).
# Used only to seed the baseline CA volume; magnitudes don't need to be exact.
REGION_DIV_PROFILE = {
    "US_LARGE":     {"yield_lo": 0.008, "yield_hi": 0.020, "events": 2},
    "EU_LARGE":     {"yield_lo": 0.010, "yield_hi": 0.025, "events": 1},
    "JP_LARGE":     {"yield_lo": 0.008, "yield_hi": 0.018, "events": 1},
    "EM_EQUITY":    {"yield_lo": 0.005, "yield_hi": 0.025, "events": 1},
    "NORDIC_SMALL": {"yield_lo": 0.005, "yield_hi": 0.020, "events": 1},
}


def generate_corporate_actions(
    dates: list[date],
) -> list[tuple[str, str, str, date, date, float, float | None, date, bool]]:
    """Returns CA rows ready to insert into corporate_actions.

    Columns: ca_id, instrument_id, ca_type, ex_date, pay_date,
             gross_amount (per share, in instrument ccy),
             ratio (None for cash divs), announced_at, applied_flag.
    """
    rng = np.random.default_rng(RANDOM_SEED ^ 0xCA)
    rows: list = []
    next_id = 1

    equities = [i for i in ALL_INSTRUMENTS if i.type == "EQUITY"]

    for instr in equities:
        profile = REGION_DIV_PROFILE.get(instr.universe_tag)
        if profile is None:
            continue

        # 60% chance of any dividend in window for funds with events==1; 90% for events==2.
        prob_any = 0.6 if profile["events"] == 1 else 0.9
        if rng.random() > prob_any:
            continue

        # Number of CAs in window.
        n_events = 1 if profile["events"] == 1 else int(rng.integers(1, 3))

        # Pick ex-dates: spread across the window with some buffer at the edges.
        if len(dates) < 10:
            continue
        usable = dates[5:-3]  # avoid first 5 and last 3 days
        chosen_idxs = rng.choice(len(usable), size=min(n_events, len(usable)),
                                 replace=False)
        for idx in sorted(chosen_idxs):
            ex_d = usable[int(idx)]
            # Pay date typically 2-4 weeks after ex-date.
            pay_offset_days = int(rng.integers(10, 25))
            # Find a business-day pay date >= ex_d + pay_offset_days, capped to last date.
            target = _add_business_days(ex_d, pay_offset_days)
            pay_d = min(target, dates[-1])

            # Per-event yield -> approximate per-share gross amount using initial price.
            ev_yield = float(rng.uniform(profile["yield_lo"], profile["yield_hi"]))
            gross = round(instr.initial_price * ev_yield, 4)

            announced = _add_business_days(ex_d, -10)
            if announced < dates[0]:
                announced = dates[0]

            rows.append((
                f"CA{next_id:06d}",
                instr.instrument_id,
                "CASH_DIV",
                ex_d,
                pay_d,
                gross,
                None,
                announced,
                True,
            ))
            next_id += 1

    return rows


def _add_business_days(d: date, n: int) -> date:
    """Add n business days to d (n can be negative). Naive (no holidays)."""
    from datetime import timedelta
    cur = d
    step = 1 if n >= 0 else -1
    remaining = abs(n)
    while remaining > 0:
        cur = cur + timedelta(days=step)
        if cur.weekday() < 5:
            remaining -= 1
    return cur


def write_corporate_actions(con, dates: list[date]) -> None:
    rows = generate_corporate_actions(dates)
    con.executemany(
        "INSERT INTO corporate_actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
