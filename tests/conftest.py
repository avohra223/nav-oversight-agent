"""Test fixtures for the tool layer.

Ensures the warehouse is built before any tool test runs. Each test session
gets a clean audit log path inside the per-session tmp dir so the real
audit/tool_calls.jsonl isn't polluted.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tools import _audit, _db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def ensure_warehouse_built() -> None:
    """Build data/nav.duckdb if it's missing."""
    db_path = ROOT / "data" / "nav.duckdb"
    if not db_path.exists():
        from nav_oversight.build import build  # noqa: WPS433
        build(verbose=False)
    assert db_path.exists(), "warehouse build did not produce data/nav.duckdb"


@pytest.fixture(scope="session", autouse=True)
def isolate_audit_log(tmp_path_factory) -> Path:
    """Redirect tool-call audit logging to a session-scoped file."""
    log = tmp_path_factory.mktemp("audit_logs") / "tool_calls.jsonl"
    _audit.set_audit_path(log)
    yield log
    # Leave the log in place; it's useful when debugging a failing test.


@pytest.fixture(autouse=True)
def reset_audit_log_per_test(isolate_audit_log) -> Path:
    """Truncate the audit log between tests so each test inspects its own
    calls cleanly."""
    isolate_audit_log.write_text("", encoding="utf-8")
    return isolate_audit_log


@pytest.fixture(scope="session")
def db_connection():
    """Read-only handle to the warehouse for tests that want to query it
    directly (e.g. to compare a tool's output to a reference query)."""
    return _db.connection()
