"""Initial portfolio construction per fund.

Picks the fund's target instruments from its universe tags, draws Dirichlet
weights, allocates AUM by weight, converts to local-ccy quantities using day-0
prices and FX. Returns initial holdings rows + initial cash rows + initial
shares-outstanding state for downstream NAV walk.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from ..config import (
    FUNDS, RANDOM_SEED, FX_VS_USD_INITIAL, START_DATE, Fund,
    DEFECT_REQUIRED_HOLDINGS, REQUIRED_INSTRUMENT_RESERVED_WEIGHT,
)
from .reference import ALL_INSTRUMENTS, INSTRUMENTS_BY_UNIVERSE


_INSTRUMENT_BY_ID = {i.instrument_id: i for i in ALL_INSTRUMENTS}


# Initial cash buffer per fund (fraction of AUM kept in base ccy as cash).
INITIAL_CASH_PCT = 0.012


@dataclass
class InitialPortfolio:
    fund_id: str
    base_ccy: str
    initial_aum_base: float
    holdings: list[tuple[str, float, float]]   # (instrument_id, qty, price_local)
    cash_base: float
    class_state: list[tuple[str, float, float]]  # (class_code, shares, nav_per_share)


def _initial_fx_to_usd(ccy: str) -> float:
    return FX_VS_USD_INITIAL[ccy]


def _fx_convert(amount: float, src_ccy: str, tgt_ccy: str) -> float:
    """Convert amount from src_ccy to tgt_ccy using day-0 USD anchors."""
    if src_ccy == tgt_ccy:
        return amount
    src_per_usd = 1.0 / _initial_fx_to_usd(src_ccy)
    tgt_per_usd = 1.0 / _initial_fx_to_usd(tgt_ccy)
    return amount * (1.0 / src_per_usd) * tgt_per_usd


def build_initial_portfolio(fund: Fund) -> InitialPortfolio:
    rng = np.random.default_rng(RANDOM_SEED ^ hash(fund.fund_id) & 0xFFFFFFFF)

    # Total class AUM in base ccy.
    total_aum = sum(c.initial_shares * c.initial_nav_per_share for c in fund.classes)

    class_state = [
        (c.code, c.initial_shares, c.initial_nav_per_share) for c in fund.classes
    ]

    # Universe pool.
    pool: list = []
    for tag in fund.target_universe:
        pool.extend(INSTRUMENTS_BY_UNIVERSE[tag])

    # Required instruments (because a defect targets them). They get a
    # reserved minimum weight; everything else is Dirichlet on the remainder.
    required_ids = DEFECT_REQUIRED_HOLDINGS.get(fund.fund_id, ())
    required_instrs = [_INSTRUMENT_BY_ID[rid] for rid in required_ids]

    pool_no_required = [i for i in pool if i.instrument_id not in required_ids]
    n_required = len(required_instrs)
    n_remaining = max(0, fund.target_n_holdings - n_required)

    if n_remaining > len(pool_no_required):
        n_remaining = len(pool_no_required)
    idxs = rng.choice(len(pool_no_required), size=n_remaining, replace=False) if n_remaining else np.array([], dtype=int)
    chosen_remaining = [pool_no_required[int(i)] for i in idxs]

    reserved_total = REQUIRED_INSTRUMENT_RESERVED_WEIGHT * n_required
    remaining_budget = max(0.0, 1.0 - reserved_total)

    weights_remaining = (
        rng.dirichlet([1.8] * n_remaining) * remaining_budget
        if n_remaining > 0 else np.array([])
    )

    chosen = required_instrs + chosen_remaining
    weights = np.concatenate([
        np.full(n_required, REQUIRED_INSTRUMENT_RESERVED_WEIGHT),
        weights_remaining,
    ])

    investable_aum = total_aum * (1.0 - INITIAL_CASH_PCT)
    cash_aum = total_aum * INITIAL_CASH_PCT

    holdings: list[tuple[str, float, float]] = []
    for instr, w in zip(chosen, weights):
        target_mv_base = float(w) * investable_aum
        target_mv_local = _fx_convert(target_mv_base, fund.base_ccy, instr.ccy)

        if instr.type == "BOND":
            # Bond MV = qty * (clean + accrued)/100 * face. Day-0 accrued is small;
            # initial accrued isn't known here so approximate with clean only.
            qty = target_mv_local / (instr.initial_price / 100.0 * (instr.face_value or 100.0))
        else:
            qty = target_mv_local / instr.initial_price

        # Round equity quantities to whole shares; bonds to nearest 1000 face.
        if instr.type == "EQUITY":
            qty = round(qty)
        else:
            qty = round(qty / 1000.0) * 1000.0

        if qty <= 0:
            continue

        holdings.append((instr.instrument_id, float(qty), instr.initial_price))

    return InitialPortfolio(
        fund_id=fund.fund_id,
        base_ccy=fund.base_ccy,
        initial_aum_base=total_aum,
        holdings=holdings,
        cash_base=cash_aum,
        class_state=class_state,
    )


def all_initial_portfolios() -> dict[str, InitialPortfolio]:
    return {f.fund_id: build_initial_portfolio(f) for f in FUNDS}


def initial_portfolio_summary() -> str:
    lines = []
    for f in FUNDS:
        p = build_initial_portfolio(f)
        lines.append(
            f"  {f.fund_id:7s} {f.base_ccy} AUM={p.initial_aum_base:,.0f} "
            f"holdings={len(p.holdings):3d} cash={p.cash_base:,.0f}"
        )
    return "\n".join(lines)
