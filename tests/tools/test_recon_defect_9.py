"""Recon test for defect 9: wrong WHT on AURORA's Samsung dividend (2026-03-12).

Reasoning chain over the public tool layer:

  1. Pull all dividend_receipts for AURORA in a window.
  2. For each receipt, look up the issuer's country (instruments) and the
     fund's domicile (fund_domiciles).
  3. Look up the (domicile, source) treaty rate (wht_treaty).
  4. Compute the implied WHT rate from gross/wht amounts (sanity check).
  5. Compare wht_rate_used to treaty_rate. A material gap means too much was
     withheld and is reclaimable.
"""
from __future__ import annotations

from datetime import date

from tools.income import get_dividend_receipts
from tools.reference import (
    get_fund_domicile, get_instruments, get_treaty_rate,
)
from tools.computation import compute_implied_wht_rate


def test_recon_defect_9_finds_excess_wht_on_aurora_samsung():
    fund_id = "AURORA"
    window = (date(2026, 3, 1), date(2026, 3, 31))

    # Step 1: receipts in window.
    receipts = get_dividend_receipts(fund_id=fund_id, date_range=window)
    assert len(receipts) >= 1

    # Step 2-5 over each receipt.
    domicile = get_fund_domicile(fund_id)
    assert domicile is not None

    findings: list[dict] = []
    MATERIAL_GAP = 0.001  # 10 bps tolerance vs treaty rate

    for r in receipts:
        # Step 2.
        instr_list = get_instruments(instrument_id=r.instrument_id)
        if not instr_list:
            continue
        issuer_country = instr_list[0].country

        # Step 3.
        treaty = get_treaty_rate(domicile, issuer_country)
        if treaty is None:
            continue

        # Step 4 (sanity): implied rate matches stored rate.
        implied_rate = compute_implied_wht_rate(r.gross_amount, r.wht_amount)
        # The two should agree to ~6 sig figs.
        assert abs(implied_rate - r.wht_rate_used) < 1e-3

        # Step 5: gap.
        gap = r.wht_rate_used - treaty.treaty_rate
        if gap > MATERIAL_GAP:
            findings.append({
                "receipt_id": r.receipt_id,
                "fund_id": r.fund_id,
                "instrument_id": r.instrument_id,
                "as_of_date": r.as_of_date,
                "domicile": domicile,
                "source_country": issuer_country,
                "treaty_rate": treaty.treaty_rate,
                "applied_rate": r.wht_rate_used,
                "gap": gap,
                "reclaimable_local": gap * r.gross_amount,
            })

    assert len(findings) == 1, (
        f"expected exactly one over-withheld receipt; found {len(findings)}: {findings}"
    )
    f = findings[0]
    assert f["instrument_id"] == "EQ_EM_SAMSU"
    assert f["as_of_date"] == date(2026, 3, 12)
    assert f["domicile"] == "LU"
    assert f["source_country"] == "KR"
    assert f["treaty_rate"] == 0.15
    assert abs(f["applied_rate"] - 0.22) < 1e-9
    assert abs(f["gap"] - 0.07) < 1e-9
    assert f["reclaimable_local"] > 0.0
