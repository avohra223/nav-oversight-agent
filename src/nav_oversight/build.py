"""Build orchestrator.

Drops `data/nav.duckdb`, recreates the schema, runs all generators in
dependency order, then runs the defect injector and a verification report.
"""
from __future__ import annotations

import time
from pathlib import Path

import duckdb

from .config import START_DATE, END_DATE, DB_PATH, DATA_DIR
from .schema import DDL, all_tables
from .generators.dates import business_days
from .generators.static_data import load_all_static
from .generators.fx import write_fx
from .generators.equity_prices import write_equity_prices
from .generators.bonds import write_bonds
from .generators.corporate_actions import write_corporate_actions
from .generators.trades import write_trades
from .generators.capstock import write_capstock
from .generators.walk import walk_forward
from .defects import (
    apply_pre_walk_defects, apply_post_walk_defects,
    update_defect_catalog_with_realized_impact,
)


def _phase(label: str):
    print(f"  -- {label} ...", end=" ", flush=True)
    return time.perf_counter()


def _done(t0: float) -> None:
    print(f"{time.perf_counter() - t0:5.2f}s")


def build(verbose: bool = True) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if Path(DB_PATH).exists():
        Path(DB_PATH).unlink()
    wal = Path(str(DB_PATH) + ".wal")
    if wal.exists():
        wal.unlink()

    if verbose:
        print(f"Building synthetic NAV warehouse at {DB_PATH}")
        print(f"  window: {START_DATE} -> {END_DATE}")

    con = duckdb.connect(str(DB_PATH))
    try:
        # Schema
        for stmt in DDL:
            con.execute(stmt)

        dates = business_days(START_DATE, END_DATE)
        if verbose:
            print(f"  business days: {len(dates)}")

        t0 = _phase("static reference data")
        load_all_static(con)
        _done(t0)

        t0 = _phase("FX time series")
        write_fx(con, dates)
        _done(t0)

        t0 = _phase("equity prices")
        write_equity_prices(con, dates)
        _done(t0)

        t0 = _phase("bond prices + accruals")
        write_bonds(con, dates)
        _done(t0)

        t0 = _phase("corporate actions")
        write_corporate_actions(con, dates)
        _done(t0)

        t0 = _phase("trades")
        write_trades(con, dates)
        _done(t0)

        t0 = _phase("capstock events")
        write_capstock(con, dates)
        _done(t0)

        t0 = _phase("inject pre-walk defects (1, 3, 4, 7)")
        apply_pre_walk_defects(con)
        _done(t0)

        t0 = _phase("walk forward (holdings, cash, fees, NAV)")
        walk_forward(con, dates)
        _done(t0)

        t0 = _phase("inject post-walk defects (2, 5, 6, 8, 9, 10)")
        apply_post_walk_defects(con)
        _done(t0)

        t0 = _phase("update defect catalog with realized impact")
        update_defect_catalog_with_realized_impact(con)
        _done(t0)

        if verbose:
            _print_quick_stats(con)
            _print_defect_report(con)

    finally:
        con.close()


def _print_quick_stats(con: duckdb.DuckDBPyConnection) -> None:
    print("\nRow counts:")
    for tbl in all_tables():
        n = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl:20s} {n:>10,d}")

    print("\nNAV summary (final day):")
    rows = con.execute(
        """
        WITH last_day AS (
            SELECT MAX(as_of_date) AS d FROM nav
        )
        SELECT n.fund_id, n.class_code, n.nav_per_share, n.nav_move_bps, n.is_break
        FROM nav n, last_day l
        WHERE n.as_of_date = l.d
        ORDER BY n.fund_id, n.class_code
        """
    ).fetchall()
    for fund_id, cc, nps, mb, brk in rows:
        flag = " BREAK" if brk else ""
        print(f"  {fund_id:7s} {cc:2s}  NAV/share={nps:>10,.4f}  d/d={mb:+7.2f}bps{flag}")

    print("\nTolerance breaks across full window:")
    breaks = con.execute(
        "SELECT COUNT(*) FROM nav WHERE is_break"
    ).fetchone()[0]
    print(f"  total break rows: {breaks}")


def _print_defect_report(con: duckdb.DuckDBPyConnection) -> None:
    print("\nDefect catalog (expected_bps_impact = realized NAV move on defect day):")
    rows = con.execute(
        """
        SELECT d.defect_id, d.code, d.fund_id, d.as_of_date, d.share_class,
               d.expected_bps_impact, f.tolerance_bps,
               COALESCE(
                   (SELECT BOOL_OR(is_break)
                    FROM nav n
                    WHERE n.fund_id = d.fund_id
                      AND n.as_of_date = d.as_of_date
                      AND (d.share_class IS NULL OR n.class_code = d.share_class)),
                   FALSE
               ) AS produced_break
        FROM defect_catalog d JOIN funds f USING (fund_id)
        ORDER BY d.as_of_date
        """
    ).fetchall()
    for did, code, fund, d, cls, impact, tol, brk in rows:
        cls_disp = cls or "*"
        impact_str = f"{impact:+8.2f}bps" if impact is not None else "    n/a   "
        flag = "BREAK   " if brk else "no-break"
        print(f"  #{did:2d} {code:26s} {fund:7s} {d}  cls={cls_disp:1s}  "
              f"NAV move {impact_str}  tol={tol:>3d}  {flag}")


if __name__ == "__main__":
    build()
