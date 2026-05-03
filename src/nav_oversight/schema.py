"""DuckDB schema for the synthetic fund-administration warehouse.

Each table is defined as a CREATE TABLE statement. The build orchestrator drops
and recreates the database from scratch every run.
"""
from __future__ import annotations

DDL: tuple[str, ...] = (
    # --- Static reference data ----------------------------------------------
    """
    CREATE TABLE funds (
        fund_id        VARCHAR PRIMARY KEY,
        name           VARCHAR NOT NULL,
        base_ccy       VARCHAR(3) NOT NULL,
        strategy       VARCHAR NOT NULL,
        tolerance_bps  INTEGER NOT NULL,
        benchmark      VARCHAR NOT NULL,
        inception_date DATE NOT NULL
    )
    """,
    """
    CREATE TABLE share_classes (
        fund_id              VARCHAR NOT NULL,
        class_code           VARCHAR NOT NULL,
        class_name           VARCHAR NOT NULL,
        mgmt_fee_bps         INTEGER NOT NULL,
        perf_fee_bps         INTEGER NOT NULL,
        has_hwm              BOOLEAN NOT NULL,
        initial_nav_per_share DOUBLE NOT NULL,
        initial_shares       DOUBLE NOT NULL,
        PRIMARY KEY (fund_id, class_code)
    )
    """,
    """
    CREATE TABLE instruments (
        instrument_id  VARCHAR PRIMARY KEY,
        ticker         VARCHAR NOT NULL,
        name           VARCHAR NOT NULL,
        type           VARCHAR NOT NULL,           -- EQUITY | BOND
        ccy            VARCHAR(3) NOT NULL,
        country        VARCHAR(2) NOT NULL,
        sector         VARCHAR,
        universe_tag   VARCHAR NOT NULL,           -- US_LARGE / EU_LARGE / JP_LARGE / EM_EQUITY / NORDIC_SMALL / IG_BOND
        coupon_rate    DOUBLE,                     -- bonds only, annual
        coupon_freq    INTEGER,                    -- bonds only, payments per year
        maturity_date  DATE,                       -- bonds only
        face_value     DOUBLE                      -- bonds only
    )
    """,
    # --- Time series --------------------------------------------------------
    """
    CREATE TABLE fx_rates (
        as_of_date  DATE NOT NULL,
        ccy         VARCHAR(3) NOT NULL,
        snap        VARCHAR NOT NULL,              -- LDN_4PM / NY_10AM / TKY_3PM / WMR_4PM
        rate_to_usd DOUBLE NOT NULL,               -- USD per 1 unit of ccy
        PRIMARY KEY (as_of_date, ccy, snap)
    )
    """,
    """
    CREATE TABLE prices (
        as_of_date    DATE NOT NULL,
        instrument_id VARCHAR NOT NULL,
        price         DOUBLE NOT NULL,              -- equity: per share; bond: clean price per 100 face
        source        VARCHAR NOT NULL,             -- PRIMARY | SECONDARY
        PRIMARY KEY (as_of_date, instrument_id, source)
    )
    """,
    """
    CREATE TABLE bond_accruals (
        as_of_date    DATE NOT NULL,
        instrument_id VARCHAR NOT NULL,
        accrued_interest_pct DOUBLE NOT NULL,      -- as % of face, accrued since last coupon
        PRIMARY KEY (as_of_date, instrument_id)
    )
    """,
    """
    CREATE TABLE corporate_actions (
        ca_id         VARCHAR PRIMARY KEY,
        instrument_id VARCHAR NOT NULL,
        ca_type       VARCHAR NOT NULL,             -- CASH_DIV | SPECIAL_DIV | STOCK_SPLIT
        ex_date       DATE NOT NULL,
        pay_date      DATE NOT NULL,
        gross_amount  DOUBLE,                       -- per share, in instrument ccy
        ratio         DOUBLE,                       -- for splits
        announced_at  DATE NOT NULL,
        applied_flag  BOOLEAN NOT NULL DEFAULT TRUE -- false => defect 3 territory
    )
    """,
    """
    CREATE TABLE wht_treaty (
        domicile_country VARCHAR(2) NOT NULL,       -- fund domicile
        source_country   VARCHAR(2) NOT NULL,       -- issuer country
        treaty_rate      DOUBLE NOT NULL,
        statutory_rate   DOUBLE NOT NULL,
        PRIMARY KEY (domicile_country, source_country)
    )
    """,
    # --- Fund domicile (used for WHT lookup) --------------------------------
    """
    CREATE TABLE fund_domiciles (
        fund_id   VARCHAR PRIMARY KEY,
        country   VARCHAR(2) NOT NULL
    )
    """,
    # --- Holdings, trades, capstock, cash, fees, NAV ------------------------
    """
    CREATE TABLE holdings (
        as_of_date    DATE NOT NULL,
        fund_id       VARCHAR NOT NULL,
        instrument_id VARCHAR NOT NULL,
        quantity      DOUBLE NOT NULL,
        price_local   DOUBLE NOT NULL,
        ccy           VARCHAR(3) NOT NULL,
        mv_local      DOUBLE NOT NULL,
        fx_to_base    DOUBLE NOT NULL,
        mv_base       DOUBLE NOT NULL,
        PRIMARY KEY (as_of_date, fund_id, instrument_id)
    )
    """,
    """
    CREATE TABLE trades (
        trade_id      VARCHAR PRIMARY KEY,
        fund_id       VARCHAR NOT NULL,
        instrument_id VARCHAR NOT NULL,
        side          VARCHAR(4) NOT NULL,          -- BUY | SELL
        quantity      DOUBLE NOT NULL,
        price         DOUBLE NOT NULL,
        ccy           VARCHAR(3) NOT NULL,
        trade_date    DATE NOT NULL,
        settle_date   DATE NOT NULL,
        broker        VARCHAR,
        booking_note  VARCHAR
    )
    """,
    """
    CREATE TABLE capstock (
        capstock_id      VARCHAR PRIMARY KEY,
        fund_id          VARCHAR NOT NULL,
        class_code       VARCHAR NOT NULL,
        as_of_date       DATE NOT NULL,
        order_received_ts TIMESTAMP NOT NULL,
        cutoff_ts         TIMESTAMP NOT NULL,
        booked_for_date   DATE NOT NULL,
        flow_type        VARCHAR(3) NOT NULL,       -- SUB | RED
        gross_amount_base DOUBLE NOT NULL,
        shares_delta     DOUBLE NOT NULL
    )
    """,
    """
    CREATE TABLE cash (
        as_of_date DATE NOT NULL,
        fund_id    VARCHAR NOT NULL,
        ccy        VARCHAR(3) NOT NULL,
        balance    DOUBLE NOT NULL,
        PRIMARY KEY (as_of_date, fund_id, ccy)
    )
    """,
    """
    CREATE TABLE fee_accruals (
        as_of_date     DATE NOT NULL,
        fund_id        VARCHAR NOT NULL,
        class_code     VARCHAR NOT NULL,
        mgmt_fee_daily DOUBLE NOT NULL,             -- in fund base ccy
        perf_fee_delta DOUBLE NOT NULL,             -- daily change in perf-fee accrual
        perf_fee_balance DOUBLE NOT NULL,           -- running balance
        hwm_nav_per_share DOUBLE,                   -- effective HWM used today
        PRIMARY KEY (as_of_date, fund_id, class_code)
    )
    """,
    """
    CREATE TABLE dividend_receipts (
        receipt_id    VARCHAR PRIMARY KEY,
        fund_id       VARCHAR NOT NULL,
        instrument_id VARCHAR NOT NULL,
        as_of_date    DATE NOT NULL,
        ccy           VARCHAR(3) NOT NULL,
        gross_amount  DOUBLE NOT NULL,
        wht_rate_used DOUBLE NOT NULL,
        wht_amount    DOUBLE NOT NULL,
        net_amount    DOUBLE NOT NULL
    )
    """,
    """
    CREATE TABLE nav (
        as_of_date       DATE NOT NULL,
        fund_id          VARCHAR NOT NULL,
        class_code       VARCHAR NOT NULL,
        gav_base         DOUBLE NOT NULL,            -- pre-fee gross asset value (class share)
        fees_accrued     DOUBLE NOT NULL,            -- total fee accrual carried (class share)
        nav_base         DOUBLE NOT NULL,            -- net asset value (class share)
        shares_outstanding DOUBLE NOT NULL,
        nav_per_share    DOUBLE NOT NULL,
        prior_nav_per_share DOUBLE,
        nav_move_bps     DOUBLE,
        is_break         BOOLEAN NOT NULL DEFAULT FALSE,
        PRIMARY KEY (as_of_date, fund_id, class_code)
    )
    """,
    # --- Defect catalog (ground truth, used by verification & demo only) ----
    """
    CREATE TABLE defect_catalog (
        defect_id       INTEGER PRIMARY KEY,
        code            VARCHAR NOT NULL,
        fund_id         VARCHAR NOT NULL,
        as_of_date      DATE NOT NULL,
        share_class     VARCHAR,
        params_json     VARCHAR NOT NULL,
        expected_bps_impact DOUBLE,
        notes           VARCHAR
    )
    """,
)


def all_tables() -> tuple[str, ...]:
    return (
        "funds", "share_classes", "instruments",
        "fx_rates", "prices", "bond_accruals",
        "corporate_actions", "wht_treaty", "fund_domiciles",
        "holdings", "trades", "capstock", "cash",
        "fee_accruals", "dividend_receipts", "nav",
        "defect_catalog",
    )
