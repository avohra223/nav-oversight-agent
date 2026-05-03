# Tool descriptions

Auto-generated from `agent/dispatcher.TOOL_REGISTRY` and the underlying
tool docstrings. Re-run `python scripts/generate_tool_descriptions.py`
after any change to a tool signature, docstring, or schema.

The agent receives these tools via the `tools=` parameter on each
Anthropic API call. This file is for human reference.

## A. Reference

### `get_fund_calendar`

Return fund-class dealing calendar (cutoff time, dealing days).

Input schema:
```json
{
  "type": "object",
  "properties": {
    "fund_id": {
      "type": "string"
    },
    "share_class": {
      "type": "string"
    }
  },
  "required": [
    "fund_id",
    "share_class"
  ]
}
```

### `get_fund_domicile`

Return ISO-2 country code where the fund is domiciled, or null if unknown.

Input schema:
```json
{
  "type": "object",
  "properties": {
    "fund_id": {
      "type": "string"
    }
  },
  "required": [
    "fund_id"
  ]
}
```

### `get_funds`

Return fund metadata (one row per fund). If fund_id is given, returns 0 or 1 row.

Input schema:
```json
{
  "type": "object",
  "properties": {
    "fund_id": {
      "type": [
        "string",
        "null"
      ],
      "description": "Optional fund_id to filter."
    }
  }
}
```

### `get_instruments`

Return instrument reference data, filtered by any combination of args.

Input schema:
```json
{
  "type": "object",
  "properties": {
    "instrument_id": {
      "type": [
        "string",
        "null"
      ]
    },
    "ticker": {
      "type": [
        "string",
        "null"
      ]
    },
    "ccy": {
      "type": [
        "string",
        "null"
      ]
    },
    "country": {
      "type": [
        "string",
        "null"
      ]
    }
  }
}
```

### `get_share_classes`

Return share classes for a fund (with mgmt/perf fee terms and HWM flag).

Input schema:
```json
{
  "type": "object",
  "properties": {
    "fund_id": {
      "type": "string"
    }
  },
  "required": [
    "fund_id"
  ]
}
```

### `get_treaty_rate`

Return treaty + statutory WHT rate for a (domicile_country, source_country) pair, or null.

Input schema:
```json
{
  "type": "object",
  "properties": {
    "domicile_country": {
      "type": "string",
      "description": "ISO-2 country (e.g. 'LU')"
    },
    "source_country": {
      "type": "string",
      "description": "ISO-2 country (e.g. 'KR')"
    }
  },
  "required": [
    "domicile_country",
    "source_country"
  ]
}
```


## B. Positions

### `get_capstock`

Return capstock events (subscriptions/redemptions) for a fund-class within a range.

Input schema:
```json
{
  "type": "object",
  "properties": {
    "fund_id": {
      "type": "string"
    },
    "share_class": {
      "type": "string"
    },
    "start_date": {
      "type": "string",
      "format": "date",
      "description": "YYYY-MM-DD"
    },
    "end_date": {
      "type": "string",
      "format": "date",
      "description": "YYYY-MM-DD"
    }
  },
  "required": [
    "fund_id",
    "share_class",
    "start_date",
    "end_date"
  ]
}
```

### `get_cash`

Return cash balances for a fund on a single date.

Input schema:
```json
{
  "type": "object",
  "properties": {
    "fund_id": {
      "type": "string"
    },
    "as_of_date": {
      "type": "string",
      "format": "date",
      "description": "YYYY-MM-DD"
    },
    "ccy": {
      "type": [
        "string",
        "null"
      ]
    }
  },
  "required": [
    "fund_id",
    "as_of_date"
  ]
}
```

### `get_holdings`

Return holdings for a fund on a single date.

Input schema:
```json
{
  "type": "object",
  "properties": {
    "fund_id": {
      "type": "string"
    },
    "as_of_date": {
      "type": "string",
      "format": "date",
      "description": "YYYY-MM-DD"
    },
    "instrument_id": {
      "type": [
        "string",
        "null"
      ]
    }
  },
  "required": [
    "fund_id",
    "as_of_date"
  ]
}
```

### `get_holdings_history`

Return time series of one position in one fund.

Input schema:
```json
{
  "type": "object",
  "properties": {
    "fund_id": {
      "type": "string"
    },
    "instrument_id": {
      "type": "string"
    },
    "start_date": {
      "type": "string",
      "format": "date",
      "description": "YYYY-MM-DD"
    },
    "end_date": {
      "type": "string",
      "format": "date",
      "description": "YYYY-MM-DD"
    }
  },
  "required": [
    "fund_id",
    "instrument_id",
    "start_date",
    "end_date"
  ]
}
```

### `get_trades`

Return trades for a fund within a date range, optionally filtered by instrument.

Input schema:
```json
{
  "type": "object",
  "properties": {
    "fund_id": {
      "type": "string"
    },
    "start_date": {
      "type": "string",
      "format": "date",
      "description": "YYYY-MM-DD"
    },
    "end_date": {
      "type": "string",
      "format": "date",
      "description": "YYYY-MM-DD"
    },
    "instrument_id": {
      "type": [
        "string",
        "null"
      ]
    }
  },
  "required": [
    "fund_id",
    "start_date",
    "end_date"
  ]
}
```


## C. Market data

### `get_bond_accruals`

Return daily accrued-interest-pct time series for one bond.

Input schema:
```json
{
  "type": "object",
  "properties": {
    "instrument_id": {
      "type": "string"
    },
    "start_date": {
      "type": "string",
      "format": "date",
      "description": "YYYY-MM-DD"
    },
    "end_date": {
      "type": "string",
      "format": "date",
      "description": "YYYY-MM-DD"
    }
  },
  "required": [
    "instrument_id",
    "start_date",
    "end_date"
  ]
}
```

### `get_fx_rate`

Return one FX rate (USD per unit of ccy) for a single date and snap.

Input schema:
```json
{
  "type": "object",
  "properties": {
    "ccy": {
      "type": "string"
    },
    "as_of_date": {
      "type": "string",
      "format": "date",
      "description": "YYYY-MM-DD"
    },
    "snap": {
      "type": "string",
      "enum": [
        "LDN_4PM",
        "NY_10AM",
        "TKY_3PM",
        "WMR_4PM"
      ]
    }
  },
  "required": [
    "ccy",
    "as_of_date"
  ]
}
```

### `get_fx_rates_all_snaps`

Return FX rates for one ccy on one date across all snaps. Use when investigating FX cutoff issues.

Input schema:
```json
{
  "type": "object",
  "properties": {
    "ccy": {
      "type": "string"
    },
    "as_of_date": {
      "type": "string",
      "format": "date",
      "description": "YYYY-MM-DD"
    }
  },
  "required": [
    "ccy",
    "as_of_date"
  ]
}
```

### `get_price_around_date`

Return prices in a window centered on a target date.

Input schema:
```json
{
  "type": "object",
  "properties": {
    "instrument_id": {
      "type": "string"
    },
    "target_date": {
      "type": "string",
      "format": "date",
      "description": "YYYY-MM-DD"
    },
    "lookback_days": {
      "type": "integer",
      "minimum": 0
    },
    "lookahead_days": {
      "type": "integer",
      "minimum": 0
    },
    "source": {
      "type": "string",
      "enum": [
        "PRIMARY",
        "SECONDARY"
      ]
    }
  },
  "required": [
    "instrument_id",
    "target_date"
  ]
}
```

### `get_price_series`

Return daily price time series for one instrument from one source ('PRIMARY' or 'SECONDARY').

Input schema:
```json
{
  "type": "object",
  "properties": {
    "instrument_id": {
      "type": "string"
    },
    "start_date": {
      "type": "string",
      "format": "date",
      "description": "YYYY-MM-DD"
    },
    "end_date": {
      "type": "string",
      "format": "date",
      "description": "YYYY-MM-DD"
    },
    "source": {
      "type": "string",
      "enum": [
        "PRIMARY",
        "SECONDARY"
      ]
    }
  },
  "required": [
    "instrument_id",
    "start_date",
    "end_date"
  ]
}
```


## D. Income / corporate actions

### `get_corporate_actions`

Return corporate actions matching filters (instrument_id / date range / ca_types).

Input schema:
```json
{
  "type": "object",
  "properties": {
    "instrument_id": {
      "type": [
        "string",
        "null"
      ]
    },
    "start_date": {
      "type": [
        "string",
        "null"
      ],
      "format": "date"
    },
    "end_date": {
      "type": [
        "string",
        "null"
      ],
      "format": "date"
    },
    "ca_types": {
      "type": [
        "array",
        "null"
      ],
      "items": {
        "type": "string",
        "enum": [
          "CASH_DIV",
          "SPECIAL_DIV",
          "STOCK_SPLIT"
        ]
      }
    }
  }
}
```

### `get_dividend_receipts`

Return dividend receipt rows matching filters.

Input schema:
```json
{
  "type": "object",
  "properties": {
    "fund_id": {
      "type": [
        "string",
        "null"
      ]
    },
    "instrument_id": {
      "type": [
        "string",
        "null"
      ]
    },
    "start_date": {
      "type": [
        "string",
        "null"
      ],
      "format": "date"
    },
    "end_date": {
      "type": [
        "string",
        "null"
      ],
      "format": "date"
    }
  }
}
```


## E. NAV / fees

### `get_fee_accruals`

Return daily fee accrual rows (mgmt + perf + HWM used) for one share class.

Input schema:
```json
{
  "type": "object",
  "properties": {
    "fund_id": {
      "type": "string"
    },
    "share_class": {
      "type": "string"
    },
    "start_date": {
      "type": "string",
      "format": "date",
      "description": "YYYY-MM-DD"
    },
    "end_date": {
      "type": "string",
      "format": "date",
      "description": "YYYY-MM-DD"
    }
  },
  "required": [
    "fund_id",
    "share_class",
    "start_date",
    "end_date"
  ]
}
```

### `get_nav_history`

Return daily NAV time series for one share class (no is_break flag projected).

Input schema:
```json
{
  "type": "object",
  "properties": {
    "fund_id": {
      "type": "string"
    },
    "share_class": {
      "type": "string"
    },
    "start_date": {
      "type": "string",
      "format": "date",
      "description": "YYYY-MM-DD"
    },
    "end_date": {
      "type": "string",
      "format": "date",
      "description": "YYYY-MM-DD"
    }
  },
  "required": [
    "fund_id",
    "share_class",
    "start_date",
    "end_date"
  ]
}
```


## F. Computation (no DB)

### `compute_expected_coupon_accrual`

Returns expected coupon accrual amount over `days` days. Conventions: ACT/365, ACT/360, 30/360.

Input schema:
```json
{
  "type": "object",
  "properties": {
    "face_value": {
      "type": "number"
    },
    "coupon_rate": {
      "type": "number",
      "description": "annual rate as decimal, e.g. 0.055"
    },
    "day_count_convention": {
      "type": "string",
      "enum": [
        "ACT/365",
        "ACT/360",
        "30/360"
      ]
    },
    "days": {
      "type": "integer"
    }
  },
  "required": [
    "face_value",
    "coupon_rate",
    "day_count_convention",
    "days"
  ]
}
```

### `compute_implied_dividend_return`

Returns the price-drop fraction implied by a per-share dividend (negative number).

Input schema:
```json
{
  "type": "object",
  "properties": {
    "gross_amount": {
      "type": "number"
    },
    "pre_ex_price": {
      "type": "number"
    }
  },
  "required": [
    "gross_amount",
    "pre_ex_price"
  ]
}
```

### `compute_implied_wht_rate`

Returns wht_amount / gross_amount.

Input schema:
```json
{
  "type": "object",
  "properties": {
    "gross_amount": {
      "type": "number"
    },
    "wht_amount": {
      "type": "number"
    }
  },
  "required": [
    "gross_amount",
    "wht_amount"
  ]
}
```

### `compute_nav_move_bps`

Day-over-day NAV move in basis points: (nav_t / nav_t_minus_1 - 1) * 1e4.

Input schema:
```json
{
  "type": "object",
  "properties": {
    "nav_t": {
      "type": "number"
    },
    "nav_t_minus_1": {
      "type": "number"
    }
  },
  "required": [
    "nav_t",
    "nav_t_minus_1"
  ]
}
```

### `compute_perf_fee`

Compute performance fee per share under HWM-with-hurdle model. Returns 0 if NAV <= hurdle-adjusted HWM.

Input schema:
```json
{
  "type": "object",
  "properties": {
    "nav_per_share": {
      "type": "number"
    },
    "hwm_nav_per_share": {
      "type": "number"
    },
    "hurdle_bps": {
      "type": "integer"
    },
    "perf_fee_bps": {
      "type": "integer"
    },
    "period_days": {
      "type": "integer"
    }
  },
  "required": [
    "nav_per_share",
    "hwm_nav_per_share",
    "perf_fee_bps",
    "period_days"
  ]
}
```

### `detect_flat_run_in_series`

Identify consecutive runs in a (date, value) series where the value is constant for at least min_length_days. RETURNS A FACT (where the series is flat), NOT A VERDICT (whether that's wrong).

Input schema:
```json
{
  "type": "object",
  "properties": {
    "series": {
      "type": "array",
      "items": {
        "type": "array",
        "prefixItems": [
          {
            "type": "string",
            "format": "date"
          },
          {
            "type": "number"
          }
        ],
        "minItems": 2,
        "maxItems": 2
      },
      "description": "Array of [YYYY-MM-DD, value] pairs sorted by date ascending."
    },
    "min_length_days": {
      "type": "integer",
      "minimum": 1
    },
    "tolerance": {
      "type": "number",
      "minimum": 0
    }
  },
  "required": [
    "series",
    "min_length_days"
  ]
}
```

