"""Load static reference data into DuckDB: funds, share_classes, instruments,
fund_domiciles, wht_treaty.
"""
from __future__ import annotations

import duckdb
import json

from ..config import FUNDS, START_DATE, DEFECT_SCHEDULE
from .reference import ALL_INSTRUMENTS, FUND_DOMICILES, WHT_TREATY


def load_funds(con: duckdb.DuckDBPyConnection) -> None:
    rows = [
        (f.fund_id, f.name, f.base_ccy, f.strategy, f.tolerance_bps,
         f.benchmark, START_DATE)
        for f in FUNDS
    ]
    con.executemany(
        "INSERT INTO funds VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )


def load_share_classes(con: duckdb.DuckDBPyConnection) -> None:
    rows = []
    for f in FUNDS:
        for c in f.classes:
            rows.append((
                f.fund_id, c.code, c.name,
                c.mgmt_fee_bps, c.perf_fee_bps, c.has_hwm,
                c.initial_nav_per_share, c.initial_shares,
            ))
    con.executemany(
        "INSERT INTO share_classes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )


def load_instruments(con: duckdb.DuckDBPyConnection) -> None:
    rows = [
        (i.instrument_id, i.ticker, i.name, i.type, i.ccy, i.country,
         i.sector, i.universe_tag,
         i.coupon_rate, i.coupon_freq, i.maturity_date, i.face_value)
        for i in ALL_INSTRUMENTS
    ]
    con.executemany(
        "INSERT INTO instruments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )


def load_fund_domiciles(con: duckdb.DuckDBPyConnection) -> None:
    rows = list(FUND_DOMICILES.items())
    con.executemany("INSERT INTO fund_domiciles VALUES (?, ?)", rows)


def load_wht_treaty(con: duckdb.DuckDBPyConnection) -> None:
    rows = [
        (dom, src, treaty, statutory)
        for (dom, src), (treaty, statutory) in WHT_TREATY.items()
    ]
    con.executemany(
        "INSERT INTO wht_treaty VALUES (?, ?, ?, ?)", rows,
    )


def load_defect_catalog(con: duckdb.DuckDBPyConnection) -> None:
    rows = [
        (d.defect_id, d.code, d.fund_id, d.as_of, d.share_class,
         json.dumps(d.params, default=str), None, None)
        for d in DEFECT_SCHEDULE
    ]
    con.executemany(
        "INSERT INTO defect_catalog VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows,
    )


def load_all_static(con: duckdb.DuckDBPyConnection) -> None:
    load_funds(con)
    load_share_classes(con)
    load_instruments(con)
    load_fund_domiciles(con)
    load_wht_treaty(con)
    load_defect_catalog(con)
