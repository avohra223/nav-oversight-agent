"""Read-only DuckDB connection management for tools.

Exposes a single helper `connection()` that lazily opens a read-only handle
to the warehouse and reuses it for the lifetime of the process. Tests can
override the database path via `set_db_path()` before any tool is called.

Tools must NOT cache results across calls; the connection is shared, results
are not.
"""
from __future__ import annotations

import threading
from pathlib import Path

import duckdb
import pandas as pd


_DEFAULT_DB_PATH = (Path(__file__).resolve().parents[1] / "data" / "nav.duckdb")
_state_lock = threading.Lock()
_state: dict = {"db_path": _DEFAULT_DB_PATH, "con": None}


# Tables that tools MUST NEVER read (ground-truth / auxiliary).
FORBIDDEN_TABLES = frozenset({"defect_catalog", "ground_truth"})


def set_db_path(path: str | Path) -> None:
    """Override the warehouse path. Must be called before connection() opens
    the handle. Closes any existing connection so the next access re-opens."""
    with _state_lock:
        if _state["con"] is not None:
            _state["con"].close()
            _state["con"] = None
        _state["db_path"] = Path(path)


def connection() -> duckdb.DuckDBPyConnection:
    """Return the shared read-only DuckDB connection. Thread-safe."""
    with _state_lock:
        if _state["con"] is None:
            _state["con"] = duckdb.connect(str(_state["db_path"]), read_only=True)
        return _state["con"]


def close_connection() -> None:
    with _state_lock:
        if _state["con"] is not None:
            _state["con"].close()
            _state["con"] = None


def coerce_date_columns(df: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    """Convert specified DataFrame columns from pd.Timestamp to python date.

    Used by tools that return DataFrames so the agent always sees `date`
    objects, matching the dataclass types returned elsewhere.
    """
    for c in columns:
        if c in df.columns and len(df) > 0:
            df[c] = pd.to_datetime(df[c]).dt.date
    return df
