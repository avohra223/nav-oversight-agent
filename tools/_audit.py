"""Tool audit logging.

`@audit_tool` decorates every tool function (DB-querying or pure compute) and
emits one JSONL line per call to `audit/tool_calls.jsonl`. The line records
timestamp, tool name, summarized input (no full payloads), summarized output
(row count and shape), latency, and error if any.

Tests assert the log is emitted on each call. The agent loop in Phase 3 will
read this file as the canonical audit trail.
"""
from __future__ import annotations

import functools
import json
import os
import threading
import time
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time as dtime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


_AUDIT_DIR = Path(__file__).resolve().parents[1] / "audit"
_AUDIT_FILE = _AUDIT_DIR / "tool_calls.jsonl"
_write_lock = threading.Lock()


def audit_path() -> Path:
    return _AUDIT_FILE


def set_audit_path(path: str | Path) -> None:
    """Override the audit log location (used in tests for isolation)."""
    global _AUDIT_FILE
    _AUDIT_FILE = Path(path)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------
def _safe(v: Any) -> Any:
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, (date, datetime, dtime)):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [_safe(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _safe(val) for k, val in v.items()}
    if is_dataclass(v) and not isinstance(v, type):
        return _safe(asdict(v))
    return f"<{type(v).__name__}>"


def _summarize_input(args: tuple, kwargs: dict) -> dict:
    return {
        "args": [_safe(a) for a in args],
        "kwargs": {k: _safe(v) for k, v in kwargs.items()},
    }


def _summarize_output(out: Any) -> dict:
    if out is None:
        return {"type": "None"}
    if isinstance(out, pd.DataFrame):
        return {
            "type": "DataFrame",
            "rows": int(out.shape[0]),
            "cols": int(out.shape[1]),
            "columns": list(out.columns.astype(str)),
        }
    if isinstance(out, list):
        n = len(out)
        elem_type = type(out[0]).__name__ if n else None
        return {"type": "list", "row_count": n, "element_type": elem_type}
    if is_dataclass(out) and not isinstance(out, type):
        return {
            "type": type(out).__name__,
            "fields": list(out.__dataclass_fields__.keys()),
        }
    if isinstance(out, (bool, int, float, str)):
        return {"type": type(out).__name__, "value": out}
    return {"type": type(out).__name__}


def _write_audit(entry: dict) -> None:
    _AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, separators=(",", ":"))
    with _write_lock:
        with _AUDIT_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------
def audit_tool(fn):
    """Wrap a tool function with structured audit logging."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter_ns()
        result: Any = None
        error: str | None = None
        try:
            result = fn(*args, **kwargs)
            return result
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            raise
        finally:
            latency_ms = round((time.perf_counter_ns() - t0) / 1e6, 3)
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "tool": fn.__module__.split(".")[-1] + "." + fn.__name__,
                "input": _summarize_input(args, kwargs),
                "output": _summarize_output(result) if error is None else None,
                "latency_ms": latency_ms,
                "error": error,
                "pid": os.getpid(),
            }
            try:
                _write_audit(entry)
            except Exception:
                # Audit failures must not break the tool call.
                pass
    return wrapper
