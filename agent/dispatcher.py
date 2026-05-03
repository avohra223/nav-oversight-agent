"""Tool dispatcher: maps LLM `tool_use` blocks to Phase 2 Python tool calls.

Each registered tool exposes:
  - an Anthropic tool definition (name, description, input_schema)
  - an arg adapter that converts LLM-friendly types (ISO date strings,
    flat tuples-as-pair-of-args) into the underlying tool's signature
  - a result serializer that turns dataclasses / DataFrames / scalars into
    a JSON-serializable structure suitable for a tool_result block

Tools that fail are wrapped: the loop receives a tool_result with
is_error=True instead of crashing.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any, Callable

import pandas as pd

from tools import (
    computation, income, market_data, nav_fees, positions, reference,
)
from tools._types import (
    AttributionLine, CapstockEvent, CashBalance, CorporateAction,
    DividendReceipt, FeeAccrual, FlatRunSegment, Fund, FundCalendar,
    FxRate, Holding, Instrument, ShareClass, Trade, TreatyRate,
)
from .schemas import ToolCall


# Cap rows returned to the agent to keep tool_result blocks manageable.
_MAX_ROWS_TO_AGENT = 200


# ---------------------------------------------------------------------------
# Result serialization
# ---------------------------------------------------------------------------
def _serialize_value(v: Any) -> Any:
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if is_dataclass(v) and not isinstance(v, type):
        return {k: _serialize_value(val) for k, val in asdict(v).items()}
    if isinstance(v, list):
        return [_serialize_value(x) for x in v]
    if isinstance(v, tuple):
        return [_serialize_value(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _serialize_value(val) for k, val in v.items()}
    return str(v)


def _serialize_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    truncated = len(df) > _MAX_ROWS_TO_AGENT
    head = df.head(_MAX_ROWS_TO_AGENT)
    records = head.to_dict(orient="records")
    records = [{k: _serialize_value(v) for k, v in r.items()} for r in records]
    return {
        "type": "DataFrame",
        "rows": int(df.shape[0]),
        "rows_returned": len(records),
        "truncated": truncated,
        "columns": list(df.columns.astype(str)),
        "records": records,
    }


def serialize_result(result: Any) -> dict[str, Any]:
    """Top-level serializer. Always returns a dict with a `type` field so
    the agent knows what to expect."""
    if result is None:
        return {"type": "None", "value": None}
    if isinstance(result, pd.DataFrame):
        return _serialize_dataframe(result)
    if isinstance(result, list):
        truncated = len(result) > _MAX_ROWS_TO_AGENT
        head = result[:_MAX_ROWS_TO_AGENT]
        return {
            "type": "list",
            "rows": len(result),
            "rows_returned": len(head),
            "truncated": truncated,
            "items": [_serialize_value(x) for x in head],
        }
    if is_dataclass(result) and not isinstance(result, type):
        return {
            "type": type(result).__name__,
            "value": _serialize_value(result),
        }
    if isinstance(result, (bool, int, float, str)):
        return {"type": type(result).__name__, "value": result}
    return {"type": type(result).__name__, "value": _serialize_value(result)}


def summarize_result(result: Any) -> dict[str, Any]:
    """Shallow summary used in audit logs (no row contents)."""
    if result is None:
        return {"type": "None"}
    if isinstance(result, pd.DataFrame):
        return {"type": "DataFrame", "rows": int(result.shape[0]),
                "cols": int(result.shape[1])}
    if isinstance(result, list):
        return {"type": "list", "rows": len(result),
                "element_type": type(result[0]).__name__ if result else None}
    if is_dataclass(result) and not isinstance(result, type):
        return {"type": type(result).__name__}
    if isinstance(result, (bool, int, float, str)):
        return {"type": type(result).__name__, "value": result}
    return {"type": type(result).__name__}


# ---------------------------------------------------------------------------
# Argument adapters
# ---------------------------------------------------------------------------
def _opt_date(s: str | None) -> date | None:
    return None if s is None else date.fromisoformat(s)


def _date(s: str) -> date:
    return date.fromisoformat(s)


def _date_range(start: str, end: str) -> tuple[date, date]:
    return (_date(start), _date(end))


# Each adapter converts the LLM's kwargs dict into the Python tool's kwargs.

def _adapt_get_funds(a: dict) -> dict:
    return {"fund_id": a.get("fund_id")}


def _adapt_get_share_classes(a: dict) -> dict:
    return {"fund_id": a["fund_id"]}


def _adapt_get_fund_domicile(a: dict) -> dict:
    return {"fund_id": a["fund_id"]}


def _adapt_get_instruments(a: dict) -> dict:
    return {
        "instrument_id": a.get("instrument_id"),
        "ticker": a.get("ticker"),
        "ccy": a.get("ccy"),
        "country": a.get("country"),
    }


def _adapt_get_treaty_rate(a: dict) -> dict:
    return {
        "domicile_country": a["domicile_country"],
        "source_country": a["source_country"],
    }


def _adapt_get_fund_calendar(a: dict) -> dict:
    return {"fund_id": a["fund_id"], "share_class": a["share_class"]}


def _adapt_get_holdings(a: dict) -> dict:
    return {
        "fund_id": a["fund_id"],
        "as_of_date": _date(a["as_of_date"]),
        "instrument_id": a.get("instrument_id"),
    }


def _adapt_get_holdings_history(a: dict) -> dict:
    return {
        "fund_id": a["fund_id"],
        "instrument_id": a["instrument_id"],
        "start_date": _date(a["start_date"]),
        "end_date": _date(a["end_date"]),
    }


def _adapt_get_trades(a: dict) -> dict:
    return {
        "fund_id": a["fund_id"],
        "date_range": _date_range(a["start_date"], a["end_date"]),
        "instrument_id": a.get("instrument_id"),
    }


def _adapt_get_cash(a: dict) -> dict:
    return {
        "fund_id": a["fund_id"],
        "as_of_date": _date(a["as_of_date"]),
        "ccy": a.get("ccy"),
    }


def _adapt_get_capstock(a: dict) -> dict:
    return {
        "fund_id": a["fund_id"],
        "share_class": a["share_class"],
        "date_range": _date_range(a["start_date"], a["end_date"]),
    }


def _adapt_get_price_series(a: dict) -> dict:
    return {
        "instrument_id": a["instrument_id"],
        "start_date": _date(a["start_date"]),
        "end_date": _date(a["end_date"]),
        "source": a.get("source", "PRIMARY"),
    }


def _adapt_get_price_around_date(a: dict) -> dict:
    return {
        "instrument_id": a["instrument_id"],
        "target_date": _date(a["target_date"]),
        "lookback_days": int(a.get("lookback_days", 5)),
        "lookahead_days": int(a.get("lookahead_days", 1)),
        "source": a.get("source", "PRIMARY"),
    }


def _adapt_get_fx_rate(a: dict) -> dict:
    return {
        "ccy": a["ccy"],
        "as_of_date": _date(a["as_of_date"]),
        "snap": a.get("snap", "LDN_4PM"),
    }


def _adapt_get_fx_rates_all_snaps(a: dict) -> dict:
    return {"ccy": a["ccy"], "as_of_date": _date(a["as_of_date"])}


def _adapt_get_bond_accruals(a: dict) -> dict:
    return {
        "instrument_id": a["instrument_id"],
        "start_date": _date(a["start_date"]),
        "end_date": _date(a["end_date"]),
    }


def _adapt_get_corporate_actions(a: dict) -> dict:
    out: dict[str, Any] = {
        "instrument_id": a.get("instrument_id"),
        "ca_types": a.get("ca_types"),
    }
    if a.get("start_date") and a.get("end_date"):
        out["date_range"] = _date_range(a["start_date"], a["end_date"])
    return out


def _adapt_get_dividend_receipts(a: dict) -> dict:
    out: dict[str, Any] = {
        "fund_id": a.get("fund_id"),
        "instrument_id": a.get("instrument_id"),
    }
    if a.get("start_date") and a.get("end_date"):
        out["date_range"] = _date_range(a["start_date"], a["end_date"])
    return out


def _adapt_get_nav_history(a: dict) -> dict:
    return {
        "fund_id": a["fund_id"],
        "share_class": a["share_class"],
        "start_date": _date(a["start_date"]),
        "end_date": _date(a["end_date"]),
    }


def _adapt_get_fee_accruals(a: dict) -> dict:
    return {
        "fund_id": a["fund_id"],
        "share_class": a["share_class"],
        "date_range": _date_range(a["start_date"], a["end_date"]),
    }


def _adapt_compute_implied_dividend_return(a: dict) -> dict:
    return {
        "gross_amount": float(a["gross_amount"]),
        "pre_ex_price": float(a["pre_ex_price"]),
    }


def _adapt_compute_implied_wht_rate(a: dict) -> dict:
    return {
        "gross_amount": float(a["gross_amount"]),
        "wht_amount": float(a["wht_amount"]),
    }


def _adapt_compute_expected_coupon_accrual(a: dict) -> dict:
    return {
        "face_value": float(a["face_value"]),
        "coupon_rate": float(a["coupon_rate"]),
        "day_count_convention": a["day_count_convention"],
        "days": int(a["days"]),
    }


def _adapt_compute_perf_fee(a: dict) -> dict:
    return {
        "nav_per_share": float(a["nav_per_share"]),
        "hwm_nav_per_share": float(a["hwm_nav_per_share"]),
        "hurdle_bps": int(a.get("hurdle_bps", 0)),
        "perf_fee_bps": int(a["perf_fee_bps"]),
        "period_days": int(a["period_days"]),
    }


def _adapt_detect_flat_run(a: dict) -> dict:
    raw = a["series"]
    series = [(date.fromisoformat(d), float(v)) for (d, v) in raw]
    return {
        "series": series,
        "min_length_days": int(a["min_length_days"]),
        "tolerance": float(a.get("tolerance", 1e-9)),
    }


def _adapt_compute_nav_move_bps(a: dict) -> dict:
    return {"nav_t": float(a["nav_t"]), "nav_t_minus_1": float(a["nav_t_minus_1"])}


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------
# Each entry: name -> (impl, adapter, json_schema, description)
def _date_str(prop_desc: str) -> dict:
    return {"type": "string", "format": "date", "description": prop_desc}


_NULLABLE_STR = {"type": ["string", "null"]}


TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    # --- Reference -----------------------------------------------------------
    "get_funds": {
        "impl": reference.get_funds,
        "adapter": _adapt_get_funds,
        "description": "Return fund metadata (one row per fund). If fund_id is given, returns 0 or 1 row.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_id": {"type": ["string", "null"], "description": "Optional fund_id to filter."}
            },
        },
    },
    "get_share_classes": {
        "impl": reference.get_share_classes,
        "adapter": _adapt_get_share_classes,
        "description": "Return share classes for a fund (with mgmt/perf fee terms and HWM flag).",
        "input_schema": {
            "type": "object",
            "properties": {"fund_id": {"type": "string"}},
            "required": ["fund_id"],
        },
    },
    "get_fund_domicile": {
        "impl": reference.get_fund_domicile,
        "adapter": _adapt_get_fund_domicile,
        "description": "Return ISO-2 country code where the fund is domiciled, or null if unknown.",
        "input_schema": {
            "type": "object",
            "properties": {"fund_id": {"type": "string"}},
            "required": ["fund_id"],
        },
    },
    "get_instruments": {
        "impl": reference.get_instruments,
        "adapter": _adapt_get_instruments,
        "description": "Return instrument reference data, filtered by any combination of args.",
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument_id": _NULLABLE_STR,
                "ticker": _NULLABLE_STR,
                "ccy": _NULLABLE_STR,
                "country": _NULLABLE_STR,
            },
        },
    },
    "get_treaty_rate": {
        "impl": reference.get_treaty_rate,
        "adapter": _adapt_get_treaty_rate,
        "description": "Return treaty + statutory WHT rate for a (domicile_country, source_country) pair, or null.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domicile_country": {"type": "string", "description": "ISO-2 country (e.g. 'LU')"},
                "source_country": {"type": "string", "description": "ISO-2 country (e.g. 'KR')"},
            },
            "required": ["domicile_country", "source_country"],
        },
    },
    "get_fund_calendar": {
        "impl": reference.get_fund_calendar,
        "adapter": _adapt_get_fund_calendar,
        "description": "Return fund-class dealing calendar (cutoff time, dealing days).",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_id": {"type": "string"},
                "share_class": {"type": "string"},
            },
            "required": ["fund_id", "share_class"],
        },
    },

    # --- Positions ----------------------------------------------------------
    "get_holdings": {
        "impl": positions.get_holdings,
        "adapter": _adapt_get_holdings,
        "description": "Return holdings for a fund on a single date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_id": {"type": "string"},
                "as_of_date": _date_str("YYYY-MM-DD"),
                "instrument_id": _NULLABLE_STR,
            },
            "required": ["fund_id", "as_of_date"],
        },
    },
    "get_holdings_history": {
        "impl": positions.get_holdings_history,
        "adapter": _adapt_get_holdings_history,
        "description": "Return time series of one position in one fund.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_id": {"type": "string"},
                "instrument_id": {"type": "string"},
                "start_date": _date_str("YYYY-MM-DD"),
                "end_date": _date_str("YYYY-MM-DD"),
            },
            "required": ["fund_id", "instrument_id", "start_date", "end_date"],
        },
    },
    "get_trades": {
        "impl": positions.get_trades,
        "adapter": _adapt_get_trades,
        "description": "Return trades for a fund within a date range, optionally filtered by instrument.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_id": {"type": "string"},
                "start_date": _date_str("YYYY-MM-DD"),
                "end_date": _date_str("YYYY-MM-DD"),
                "instrument_id": _NULLABLE_STR,
            },
            "required": ["fund_id", "start_date", "end_date"],
        },
    },
    "get_cash": {
        "impl": positions.get_cash,
        "adapter": _adapt_get_cash,
        "description": "Return cash balances for a fund on a single date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_id": {"type": "string"},
                "as_of_date": _date_str("YYYY-MM-DD"),
                "ccy": _NULLABLE_STR,
            },
            "required": ["fund_id", "as_of_date"],
        },
    },
    "get_capstock": {
        "impl": positions.get_capstock,
        "adapter": _adapt_get_capstock,
        "description": "Return capstock events (subscriptions/redemptions) for a fund-class within a range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_id": {"type": "string"},
                "share_class": {"type": "string"},
                "start_date": _date_str("YYYY-MM-DD"),
                "end_date": _date_str("YYYY-MM-DD"),
            },
            "required": ["fund_id", "share_class", "start_date", "end_date"],
        },
    },

    # --- Market data --------------------------------------------------------
    "get_price_series": {
        "impl": market_data.get_price_series,
        "adapter": _adapt_get_price_series,
        "description": "Return daily price time series for one instrument from one source ('PRIMARY' or 'SECONDARY').",
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument_id": {"type": "string"},
                "start_date": _date_str("YYYY-MM-DD"),
                "end_date": _date_str("YYYY-MM-DD"),
                "source": {"type": "string", "enum": ["PRIMARY", "SECONDARY"]},
            },
            "required": ["instrument_id", "start_date", "end_date"],
        },
    },
    "get_price_around_date": {
        "impl": market_data.get_price_around_date,
        "adapter": _adapt_get_price_around_date,
        "description": "Return prices in a window centered on a target date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument_id": {"type": "string"},
                "target_date": _date_str("YYYY-MM-DD"),
                "lookback_days": {"type": "integer", "minimum": 0},
                "lookahead_days": {"type": "integer", "minimum": 0},
                "source": {"type": "string", "enum": ["PRIMARY", "SECONDARY"]},
            },
            "required": ["instrument_id", "target_date"],
        },
    },
    "get_fx_rate": {
        "impl": market_data.get_fx_rate,
        "adapter": _adapt_get_fx_rate,
        "description": "Return one FX rate (USD per unit of ccy) for a single date and snap.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ccy": {"type": "string"},
                "as_of_date": _date_str("YYYY-MM-DD"),
                "snap": {"type": "string", "enum": ["LDN_4PM", "NY_10AM", "TKY_3PM", "WMR_4PM"]},
            },
            "required": ["ccy", "as_of_date"],
        },
    },
    "get_fx_rates_all_snaps": {
        "impl": market_data.get_fx_rates_all_snaps,
        "adapter": _adapt_get_fx_rates_all_snaps,
        "description": "Return FX rates for one ccy on one date across all snaps. Use when investigating FX cutoff issues.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ccy": {"type": "string"},
                "as_of_date": _date_str("YYYY-MM-DD"),
            },
            "required": ["ccy", "as_of_date"],
        },
    },
    "get_bond_accruals": {
        "impl": market_data.get_bond_accruals,
        "adapter": _adapt_get_bond_accruals,
        "description": "Return daily accrued-interest-pct time series for one bond.",
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument_id": {"type": "string"},
                "start_date": _date_str("YYYY-MM-DD"),
                "end_date": _date_str("YYYY-MM-DD"),
            },
            "required": ["instrument_id", "start_date", "end_date"],
        },
    },

    # --- Income -------------------------------------------------------------
    "get_corporate_actions": {
        "impl": income.get_corporate_actions,
        "adapter": _adapt_get_corporate_actions,
        "description": "Return corporate actions matching filters (instrument_id / date range / ca_types).",
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument_id": _NULLABLE_STR,
                "start_date": {"type": ["string", "null"], "format": "date"},
                "end_date": {"type": ["string", "null"], "format": "date"},
                "ca_types": {
                    "type": ["array", "null"],
                    "items": {"type": "string", "enum": ["CASH_DIV", "SPECIAL_DIV", "STOCK_SPLIT"]},
                },
            },
        },
    },
    "get_dividend_receipts": {
        "impl": income.get_dividend_receipts,
        "adapter": _adapt_get_dividend_receipts,
        "description": "Return dividend receipt rows matching filters.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_id": _NULLABLE_STR,
                "instrument_id": _NULLABLE_STR,
                "start_date": {"type": ["string", "null"], "format": "date"},
                "end_date": {"type": ["string", "null"], "format": "date"},
            },
        },
    },

    # --- NAV / fees ---------------------------------------------------------
    "get_nav_history": {
        "impl": nav_fees.get_nav_history,
        "adapter": _adapt_get_nav_history,
        "description": "Return daily NAV time series for one share class (no is_break flag projected).",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_id": {"type": "string"},
                "share_class": {"type": "string"},
                "start_date": _date_str("YYYY-MM-DD"),
                "end_date": _date_str("YYYY-MM-DD"),
            },
            "required": ["fund_id", "share_class", "start_date", "end_date"],
        },
    },
    "get_fee_accruals": {
        "impl": nav_fees.get_fee_accruals,
        "adapter": _adapt_get_fee_accruals,
        "description": "Return daily fee accrual rows (mgmt + perf + HWM used) for one share class.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fund_id": {"type": "string"},
                "share_class": {"type": "string"},
                "start_date": _date_str("YYYY-MM-DD"),
                "end_date": _date_str("YYYY-MM-DD"),
            },
            "required": ["fund_id", "share_class", "start_date", "end_date"],
        },
    },

    # --- Computation (no DB) -----------------------------------------------
    "compute_implied_dividend_return": {
        "impl": computation.compute_implied_dividend_return,
        "adapter": _adapt_compute_implied_dividend_return,
        "description": "Returns the price-drop fraction implied by a per-share dividend (negative number).",
        "input_schema": {
            "type": "object",
            "properties": {
                "gross_amount": {"type": "number"},
                "pre_ex_price": {"type": "number"},
            },
            "required": ["gross_amount", "pre_ex_price"],
        },
    },
    "compute_implied_wht_rate": {
        "impl": computation.compute_implied_wht_rate,
        "adapter": _adapt_compute_implied_wht_rate,
        "description": "Returns wht_amount / gross_amount.",
        "input_schema": {
            "type": "object",
            "properties": {
                "gross_amount": {"type": "number"},
                "wht_amount": {"type": "number"},
            },
            "required": ["gross_amount", "wht_amount"],
        },
    },
    "compute_expected_coupon_accrual": {
        "impl": computation.compute_expected_coupon_accrual,
        "adapter": _adapt_compute_expected_coupon_accrual,
        "description": "Returns expected coupon accrual amount over `days` days. Conventions: ACT/365, ACT/360, 30/360.",
        "input_schema": {
            "type": "object",
            "properties": {
                "face_value": {"type": "number"},
                "coupon_rate": {"type": "number", "description": "annual rate as decimal, e.g. 0.055"},
                "day_count_convention": {"type": "string", "enum": ["ACT/365", "ACT/360", "30/360"]},
                "days": {"type": "integer"},
            },
            "required": ["face_value", "coupon_rate", "day_count_convention", "days"],
        },
    },
    "compute_perf_fee": {
        "impl": computation.compute_perf_fee,
        "adapter": _adapt_compute_perf_fee,
        "description": "Compute performance fee per share under HWM-with-hurdle model. Returns 0 if NAV <= hurdle-adjusted HWM.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nav_per_share": {"type": "number"},
                "hwm_nav_per_share": {"type": "number"},
                "hurdle_bps": {"type": "integer"},
                "perf_fee_bps": {"type": "integer"},
                "period_days": {"type": "integer"},
            },
            "required": ["nav_per_share", "hwm_nav_per_share", "perf_fee_bps", "period_days"],
        },
    },
    "detect_flat_run_in_series": {
        "impl": computation.detect_flat_run_in_series,
        "adapter": _adapt_detect_flat_run,
        "description": (
            "Identify consecutive runs in a (date, value) series where the value is constant for "
            "at least min_length_days. RETURNS A FACT (where the series is flat), NOT A VERDICT "
            "(whether that's wrong)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "series": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "prefixItems": [
                            {"type": "string", "format": "date"},
                            {"type": "number"},
                        ],
                        "minItems": 2, "maxItems": 2,
                    },
                    "description": "Array of [YYYY-MM-DD, value] pairs sorted by date ascending.",
                },
                "min_length_days": {"type": "integer", "minimum": 1},
                "tolerance": {"type": "number", "minimum": 0},
            },
            "required": ["series", "min_length_days"],
        },
    },
    "compute_nav_move_bps": {
        "impl": computation.compute_nav_move_bps,
        "adapter": _adapt_compute_nav_move_bps,
        "description": "Day-over-day NAV move in basis points: (nav_t / nav_t_minus_1 - 1) * 1e4.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nav_t": {"type": "number"},
                "nav_t_minus_1": {"type": "number"},
            },
            "required": ["nav_t", "nav_t_minus_1"],
        },
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def build_anthropic_tool_definitions(cache_last: bool = True) -> list[dict[str, Any]]:
    """Build the list of tool definitions for the Anthropic API.

    If `cache_last` is True, attaches cache_control to the last tool so the
    full tools block participates in prompt caching.
    """
    defs: list[dict[str, Any]] = []
    for name, spec in TOOL_REGISTRY.items():
        defs.append({
            "name": name,
            "description": spec["description"],
            "input_schema": spec["input_schema"],
        })
    if cache_last and defs:
        defs[-1]["cache_control"] = {"type": "ephemeral"}
    return defs


def dispatch(
    tool_name: str, raw_args: dict[str, Any], iteration: int,
    tool_use_id: str | None = None,
) -> tuple[dict[str, Any], ToolCall]:
    """Execute a tool by name with LLM-supplied raw_args.

    Returns (tool_result_content, ToolCall_record).
    Tool errors do not raise; they are returned as is_error tool_results.
    """
    spec = TOOL_REGISTRY.get(tool_name)
    if spec is None:
        err = f"unknown tool {tool_name!r}"
        return (
            {"is_error": True, "error_type": "UnknownTool", "message": err},
            ToolCall(
                iteration=iteration, tool_name=tool_name, arguments=raw_args,
                result_summary={"error": err}, latency_ms=0.0,
                error=err, tool_use_id=tool_use_id,
            ),
        )

    t0 = time.perf_counter_ns()
    try:
        kwargs = spec["adapter"](raw_args)
        result = spec["impl"](**kwargs)
    except Exception as e:
        latency_ms = (time.perf_counter_ns() - t0) / 1e6
        msg = f"{type(e).__name__}: {e}"
        return (
            {"is_error": True, "error_type": type(e).__name__, "message": msg},
            ToolCall(
                iteration=iteration, tool_name=tool_name, arguments=raw_args,
                result_summary={"error": msg}, latency_ms=latency_ms,
                error=msg, tool_use_id=tool_use_id,
            ),
        )

    latency_ms = (time.perf_counter_ns() - t0) / 1e6
    payload = serialize_result(result)
    summary = summarize_result(result)
    return (
        payload,
        ToolCall(
            iteration=iteration, tool_name=tool_name, arguments=raw_args,
            result_summary=summary, latency_ms=latency_ms,
            tool_use_id=tool_use_id,
        ),
    )
