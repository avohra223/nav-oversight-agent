"""Recon test for defect 3: missed corporate action (HELIO AAPL 2026-04-02).

This test reproduces the multi-step reasoning the agent will do, using ONLY
the public tool layer. It must NOT touch corporate_actions.applied_flag,
nav.is_break, or any ground-truth column.

The reasoning chain (in plain Python; this simulates the agent):

  1. Pull all CASH_DIV / SPECIAL_DIV CAs in a window around the suspected day.
  2. For each CA, ask: did HELIO hold the underlying on ex_date?
  3. If yes, did the price drop by approximately gross_amount / pre_ex_price?
     (This corroborates that the CA actually happened in the market.)
  4. Was a dividend receipt booked for HELIO + instrument + pay_date?
  5. If price-drop confirms the CA AND no receipt exists, that's the defect.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from tools.income import get_corporate_actions, get_dividend_receipts
from tools.market_data import get_price_around_date
from tools.positions import get_holdings
from tools.computation import compute_implied_dividend_return


def _pre_ex_price(price_df: pd.DataFrame, ex_date: date) -> float:
    pre = price_df[price_df["as_of_date"] < ex_date]
    return float(pre.iloc[-1]["price"]) if len(pre) > 0 else float("nan")


def _on_ex_price(price_df: pd.DataFrame, ex_date: date) -> float:
    on = price_df[price_df["as_of_date"] == ex_date]
    return float(on.iloc[0]["price"]) if len(on) > 0 else float("nan")


def test_recon_defect_3_finds_missed_ca_on_helio_aapl():
    fund_id = "HELIO"
    window = (date(2026, 4, 1), date(2026, 4, 5))

    # Step 1: collect candidate CAs.
    cas = get_corporate_actions(
        date_range=window, ca_types=["CASH_DIV", "SPECIAL_DIV"],
    )
    assert len(cas) >= 1, "expected at least one CA in window"

    findings: list[dict] = []
    for ca in cas:
        # Step 2: was the fund holding it?
        held = get_holdings(fund_id, ca.ex_date, instrument_id=ca.instrument_id)
        if not held or held[0].quantity <= 0:
            continue
        qty = held[0].quantity

        # Step 3: did the price drop consistent with the dividend?
        prices = get_price_around_date(
            ca.instrument_id, ca.ex_date, lookback_days=3, lookahead_days=0,
        )
        pre = _pre_ex_price(prices, ca.ex_date)
        on_ex = _on_ex_price(prices, ca.ex_date)
        if pre != pre or on_ex != on_ex:   # NaN check
            continue
        realized = (on_ex - pre) / pre
        implied = compute_implied_dividend_return(
            ca.gross_amount or 0.0, pre,
        )

        # Step 4: was the receipt booked?
        receipts = get_dividend_receipts(
            fund_id=fund_id,
            instrument_id=ca.instrument_id,
            date_range=(ca.pay_date, ca.pay_date),
        )

        # Step 5: agent's conclusion -- price-drop confirms the CA AND no receipt.
        # Threshold: realized return is at least half of the implied drop AND
        # is itself a meaningful negative number.
        ca_actually_happened = (
            realized < 0
            and abs(realized - implied) / max(abs(implied), 1e-9) < 0.5
        )
        receipt_missing = len(receipts) == 0

        if ca_actually_happened and receipt_missing:
            findings.append({
                "ca_id": ca.ca_id,
                "instrument_id": ca.instrument_id,
                "ex_date": ca.ex_date,
                "shares_held": qty,
                "pre_ex_price": pre,
                "on_ex_price": on_ex,
                "realized_return": realized,
                "implied_return": implied,
                "expected_gross_receipt": qty * (ca.gross_amount or 0.0),
            })

    # Assertions.
    assert len(findings) == 1, (
        f"expected exactly one missed CA; found {len(findings)}: {findings}"
    )
    f = findings[0]
    assert f["instrument_id"] == "EQ_US_AAPL"
    assert f["ex_date"] == date(2026, 4, 2)
    # Realized drop should be close to implied (within 30% of implied magnitude).
    assert abs(f["realized_return"] - f["implied_return"]) < abs(f["implied_return"]) * 0.3
    # Expected receipt amount is non-trivial.
    assert f["expected_gross_receipt"] > 1000.0
