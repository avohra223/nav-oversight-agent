"""Capstock event generator -- subscriptions and redemptions per share class.

Each event has order_received_ts vs cutoff_ts. In baseline data, all orders
arrive before cutoff (compliant). The defect-8 injector overrides ATLAS Class A
on 2026-03-05 to plant a post-cutoff order that was wrongly stamped pre-cutoff.

Subscriptions / redemptions in baseline are sized as small % of class AUM,
typical of institutional flow.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

import numpy as np

from ..config import FUNDS, RANDOM_SEED


@dataclass
class CapstockEvent:
    capstock_id: str
    fund_id: str
    class_code: str
    as_of_date: date
    order_received_ts: datetime
    cutoff_ts: datetime
    booked_for_date: date
    flow_type: str              # SUB | RED
    gross_amount_base: float
    shares_delta: float = 0.0   # filled later in walk-forward (depends on NAV)


# Cutoff time for all funds in v0 (12:00 local; we use a single timestamp for simplicity).
CUTOFF_TIME = time(12, 0)


def generate_capstock_events(dates: list[date]) -> list[CapstockEvent]:
    rng = np.random.default_rng(RANDOM_SEED ^ 0xCA9B)
    events: list[CapstockEvent] = []
    next_id = 1

    for f in FUNDS:
        for c in f.classes:
            class_aum = c.initial_shares * c.initial_nav_per_share
            for d in dates:
                # ~30% of days have any capstock; biased toward small flows.
                if rng.random() > 0.30:
                    continue
                # 1 event normally; occasionally 2.
                n_events = 1 if rng.random() < 0.85 else 2
                for _ in range(n_events):
                    flow_type = "SUB" if rng.random() < 0.55 else "RED"
                    # Size: most events 5-50 bps of AUM; ~5% are larger (50-200 bps).
                    if rng.random() < 0.05:
                        size_pct = float(rng.uniform(0.005, 0.020))
                    else:
                        size_pct = float(rng.uniform(0.0005, 0.0050))
                    gross = round(class_aum * size_pct, 2)

                    # Order received: random hour 8-14 local; baseline always
                    # before cutoff at 12:00. So restrict to 8-11:30.
                    minutes_before_cutoff = int(rng.integers(15, 240))
                    order_dt = datetime.combine(d, CUTOFF_TIME) - _td_minutes(minutes_before_cutoff)
                    cutoff_dt = datetime.combine(d, CUTOFF_TIME)

                    events.append(CapstockEvent(
                        capstock_id=f"CS{next_id:07d}",
                        fund_id=f.fund_id,
                        class_code=c.code,
                        as_of_date=d,
                        order_received_ts=order_dt,
                        cutoff_ts=cutoff_dt,
                        booked_for_date=d,
                        flow_type=flow_type,
                        gross_amount_base=gross,
                    ))
                    next_id += 1

    return events


def _td_minutes(m: int):
    from datetime import timedelta
    return timedelta(minutes=m)


def write_capstock(con, dates: list[date]) -> None:
    events = generate_capstock_events(dates)
    rows = [
        (e.capstock_id, e.fund_id, e.class_code, e.as_of_date,
         e.order_received_ts, e.cutoff_ts, e.booked_for_date,
         e.flow_type, e.gross_amount_base, e.shares_delta)
        for e in events
    ]
    con.executemany(
        "INSERT INTO capstock VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows,
    )
