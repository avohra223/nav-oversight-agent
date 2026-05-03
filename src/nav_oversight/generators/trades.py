"""Trade generator.

Per fund per business day, generate 0-3 trades. Trades are sized as a small
fraction of AUM (5-50 bps) and pick instruments from the fund's existing
holdings or its universe. Sides are random (BUY / SELL).

Trades settle T+0 in v0 (cash impact same day as trade) to simplify the
walk-forward NAV calc.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from ..config import FUNDS, RANDOM_SEED
from .reference import ALL_INSTRUMENTS, INSTRUMENTS_BY_UNIVERSE


@dataclass
class TradeEvent:
    trade_id: str
    fund_id: str
    instrument_id: str
    side: str
    quantity: float
    price: float          # placeholder; final price filled in during walk-forward
    ccy: str
    trade_date: date
    settle_date: date
    broker: str
    booking_note: str = ""


def _random_broker(rng: np.random.Generator) -> str:
    return str(rng.choice(["GS", "MS", "JPM", "UBS", "CS", "BARC", "SOC"]))


def generate_trade_events(dates: list[date]) -> list[TradeEvent]:
    rng = np.random.default_rng(RANDOM_SEED ^ 0x7AAD)
    events: list[TradeEvent] = []
    next_id = 1

    instrs_by_universe = {
        tag: list(INSTRUMENTS_BY_UNIVERSE[tag]) for tag in INSTRUMENTS_BY_UNIVERSE
    }

    for f in FUNDS:
        # Build the fund's eligible instrument pool.
        pool: list = []
        for tag in f.target_universe:
            pool.extend(instrs_by_universe[tag])
        # Approximate fund AUM in base ccy from initial class state.
        approx_aum = sum(c.initial_shares * c.initial_nav_per_share for c in f.classes)

        for d in dates:
            # 60% of days have any trade.
            if rng.random() > 0.60:
                continue
            n_trades = int(rng.choice([1, 1, 1, 2, 3]))
            for _ in range(n_trades):
                instr = pool[int(rng.integers(0, len(pool)))]
                side = "BUY" if rng.random() < 0.55 else "SELL"
                trade_aum_pct = float(rng.uniform(0.0005, 0.0050))
                trade_size_base = approx_aum * trade_aum_pct
                # Convert to local quantity using approximate initial price.
                if instr.type == "EQUITY":
                    qty = max(1, round(trade_size_base / instr.initial_price))
                else:
                    qty = max(1000.0, round(trade_size_base / (instr.initial_price / 100.0 * (instr.face_value or 100.0)) / 1000.0) * 1000.0)
                events.append(TradeEvent(
                    trade_id=f"TR{next_id:07d}",
                    fund_id=f.fund_id,
                    instrument_id=instr.instrument_id,
                    side=side,
                    quantity=float(qty),
                    price=instr.initial_price,
                    ccy=instr.ccy,
                    trade_date=d,
                    settle_date=d,  # T+0 in v0
                    broker=_random_broker(rng),
                ))
                next_id += 1

    return events


def write_trades(con, dates: list[date]) -> None:
    events = generate_trade_events(dates)
    rows = [
        (e.trade_id, e.fund_id, e.instrument_id, e.side, e.quantity, e.price,
         e.ccy, e.trade_date, e.settle_date, e.broker, e.booking_note)
        for e in events
    ]
    con.executemany(
        "INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows,
    )
