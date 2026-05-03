"""Print the demo scenarios the agent will be expected to investigate.

Two categories:
  1. Tolerance breaks (nav.is_break = TRUE) -- the agent's primary feed.
  2. Sub-tolerance defects (recon, accrual time-series, cross-class divergence,
     WHT compliance) -- the agent's secondary anomaly checks.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import duckdb  # noqa: E402

from nav_oversight.config import DB_PATH, DEFECT_SCHEDULE  # noqa: E402


def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)

    print("=" * 78)
    print("NAV OVERSIGHT WAREHOUSE -- SCENARIO INDEX")
    print("=" * 78)

    print("\n[1] Tolerance breaks (nav.is_break = TRUE)")
    print("-" * 78)
    rows = con.execute(
        """
        SELECT n.as_of_date, n.fund_id, n.class_code, ROUND(n.nav_move_bps, 1) AS bps,
               f.tolerance_bps,
               CASE WHEN d.defect_id IS NOT NULL THEN 'DEFECT #' || d.defect_id || ' ' || d.code
                    ELSE 'baseline noise' END AS source
        FROM nav n JOIN funds f USING (fund_id)
        LEFT JOIN defect_catalog d ON d.fund_id = n.fund_id AND d.as_of_date = n.as_of_date
                                  AND (d.share_class IS NULL OR d.share_class = n.class_code)
        WHERE n.is_break
        ORDER BY n.as_of_date, n.fund_id
        """
    ).fetchall()
    for r in rows:
        print(f"  {r[0]}  {r[1]:7s} {r[2]:1s}  d/d {r[3]:>+8.1f}bps  tol={r[4]:>3d}  {r[5]}")

    print("\n[2] Sub-tolerance defects (require specialized anomaly detectors)")
    print("-" * 78)

    # Defect 6: trade vs position-delta mismatch.
    print("\n  Defect 6 -- trade booked on wrong side (HELIO 2026-02-04)")
    row = con.execute(
        "SELECT trade_id, side, quantity, instrument_id, booking_note "
        "FROM trades WHERE booking_note LIKE 'DEFECT_6%'"
    ).fetchone()
    if row:
        print(f"    Smoking gun: trade {row[0]} flipped {row[4]} -> recorded as {row[1]} "
              f"{row[2]:.0f} of {row[3]}")
        print("    Detection: cross-check trades.side vs holdings delta on trade_date.")

    # Defect 7: bond accrual frozen.
    print("\n  Defect 7 -- missed coupon accrual (STERL BARC bond, 4 days)")
    rows = con.execute(
        "SELECT as_of_date, ROUND(accrued_interest_pct, 4) "
        "FROM bond_accruals WHERE instrument_id='BND_GBP_BARC_2031' "
        "AND as_of_date BETWEEN '2026-03-17' AND '2026-03-26' "
        "ORDER BY as_of_date"
    ).fetchall()
    for r in rows:
        print(f"    {r[0]}  accrued = {r[1]}%")
    print("    Detection: accrued_interest_pct should tick up daily; flat for 4 days "
          "is a feed/processing failure.")

    # Defect 8: capstock timestamp anomaly + cross-class divergence.
    print("\n  Defect 8 -- subscription stamped pre-cutoff (ATLAS Class A 2026-03-05)")
    cap = con.execute(
        "SELECT capstock_id, order_received_ts, cutoff_ts, gross_amount_base "
        "FROM capstock WHERE capstock_id = 'CS_DEFECT_8'"
    ).fetchone()
    if cap:
        print(f"    Smoking gun: {cap[0]} order received {cap[1]} but cutoff is {cap[2]}; "
              f"booked anyway for ${cap[3]:,.0f}")
    cls = con.execute(
        "SELECT class_code, ROUND(nav_move_bps, 1) "
        "FROM nav WHERE fund_id='ATLAS' AND as_of_date='2026-03-05' ORDER BY class_code"
    ).fetchall()
    print(f"    Cross-class divergence: " + "  ".join(
        f"Class {c}: {b:+.1f}bps" for c, b in cls
    ))
    print("    Detection: order_received_ts > cutoff_ts AND booked_for_date == as_of_date.")

    # Defect 9: WHT compliance.
    print("\n  Defect 9 -- wrong WHT on Samsung dividend (AURORA 2026-03-12)")
    row = con.execute(
        """
        SELECT dr.gross_amount, dr.wht_rate_used, t.treaty_rate, t.statutory_rate,
               i.country, fd.country
        FROM dividend_receipts dr
        JOIN instruments i ON i.instrument_id = dr.instrument_id
        JOIN fund_domiciles fd ON fd.fund_id = dr.fund_id
        JOIN wht_treaty t ON t.domicile_country = fd.country AND t.source_country = i.country
        WHERE dr.fund_id='AURORA' AND dr.instrument_id='EQ_EM_SAMSU' AND dr.as_of_date='2026-03-12'
        """
    ).fetchone()
    if row:
        gross, used, treaty, statutory, src, dom = row
        print(f"    {dom} fund received {src} dividend; treaty={treaty*100:.0f}%, "
              f"statutory={statutory*100:.0f}%, applied={used*100:.0f}%")
        gap = (used - treaty) * gross
        print(f"    Reclaimable: ({used*100:.0f}% - {treaty*100:.0f}%) x gross = "
              f"{gap:,.0f} {src} (pre-FX)")
        print("    Detection: dividend_receipts.wht_rate_used vs wht_treaty(domicile, source).")

    # Defect 10: cross-class fee divergence.
    print("\n  Defect 10 -- share-class fee misallocation (ATLAS Class I 2026-04-23)")
    rows = con.execute(
        """
        SELECT fa.class_code, ROUND(fa.mgmt_fee_daily, 2), ROUND(n.nav_move_bps, 2)
        FROM fee_accruals fa JOIN nav n USING (as_of_date, fund_id, class_code)
        WHERE fa.fund_id='ATLAS' AND fa.as_of_date='2026-04-23'
        ORDER BY fa.class_code
        """
    ).fetchall()
    for r in rows:
        print(f"    Class {r[0]}  mgmt_fee=${r[1]:.2f}  NAV move={r[2]:+.2f}bps")
    print("    Detection: Class I daily mgmt fee should be ~ AUM_I * 60bps/365; ")
    print("               compare expected vs booked, also compare A vs I move ratio.")

    print()
    print("=" * 78)
    print("Total seeded defects: 10")
    print(f"  Tolerance breaks: {sum(1 for r in rows if False)}", end="")
    n_breaks = con.execute(
        "SELECT COUNT(*) FROM defect_catalog d JOIN nav n "
        "ON d.fund_id=n.fund_id AND d.as_of_date=n.as_of_date "
        "WHERE n.is_break"
    ).fetchone()[0]
    print(f"  {n_breaks} of 10 produce tolerance breaks.")
    print(f"  Remaining {10 - n_breaks} are sub-tolerance, detected via anomaly checks.")
    print("=" * 78)
    con.close()


if __name__ == "__main__":
    main()
