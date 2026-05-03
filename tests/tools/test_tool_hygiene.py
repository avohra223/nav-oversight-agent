"""Hygiene linter for the tool layer.

Scans every .py file in /tools for:
  1. Forbidden columns being projected from SQL strings.
  2. Forbidden table names appearing anywhere.
  3. Tool function names starting with forbidden prefixes
     (with one explicit allow-list entry).

Failure of this test means a tool would leak ground truth or embed a verdict.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"

FORBIDDEN_COLUMNS = (
    "applied_flag",
    "is_break",
    "booking_note",
)
FORBIDDEN_TABLES = (
    "defect_catalog",
    "ground_truth",
)
FORBIDDEN_PREFIXES = ("detect_", "check_", "validate_", "find_", "is_")
PREFIX_ALLOWLIST = {"detect_flat_run_in_series"}


def _public_py_files():
    """All .py files in tools/ EXCEPT __init__ and dunder-prefixed helpers."""
    for p in sorted(TOOLS_DIR.glob("*.py")):
        if p.name.startswith("_") or p.name == "__init__.py":
            continue
        yield p


def _string_literals(node: ast.AST):
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            yield n.value


def test_no_forbidden_columns_projected():
    offenders: list[tuple[str, str, str]] = []
    for path in _public_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for s in _string_literals(tree):
            up = s.upper()
            if "SELECT" not in up:
                continue
            for col in FORBIDDEN_COLUMNS:
                # Match as a whole word so 'is_break' doesn't match 'IS' inside 'IS NULL'.
                if re.search(rf"\b{re.escape(col)}\b", s):
                    offenders.append((path.name, col, s.strip().splitlines()[0][:80]))
    assert not offenders, (
        "Forbidden columns projected by tool SQL:\n"
        + "\n".join(f"  {fn}: {col} in {snippet!r}" for fn, col, snippet in offenders)
    )


def test_no_forbidden_tables_referenced():
    offenders: list[tuple[str, str]] = []
    for path in _public_py_files():
        text = path.read_text(encoding="utf-8")
        for tbl in FORBIDDEN_TABLES:
            if re.search(rf"\b{re.escape(tbl)}\b", text):
                offenders.append((path.name, tbl))
    assert not offenders, (
        "Forbidden tables referenced from tool modules:\n"
        + "\n".join(f"  {fn}: {tbl}" for fn, tbl in offenders)
    )


def test_no_verdict_prefixed_tool_names():
    offenders: list[tuple[str, str]] = []
    for path in _public_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if not isinstance(n, ast.FunctionDef):
                continue
            if n.name.startswith("_"):
                continue
            if n.name in PREFIX_ALLOWLIST:
                continue
            for prefix in FORBIDDEN_PREFIXES:
                if n.name.startswith(prefix):
                    offenders.append((path.name, n.name))
                    break
    assert not offenders, (
        "Tool functions named with verdict-shaped prefixes "
        "(detect_/check_/validate_/find_/is_):\n"
        + "\n".join(f"  {fn}: {name}" for fn, name in offenders)
    )


def test_only_parameterized_sql():
    """Heuristic: SQL strings should not contain f-string expressions or
    .format() calls, both of which suggest non-parameterized injection."""
    offenders: list[tuple[str, str]] = []
    for path in _public_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            # f-strings whose content looks like SQL
            if isinstance(n, ast.JoinedStr):
                rendered = "".join(
                    v.value for v in n.values if isinstance(v, ast.Constant) and isinstance(v.value, str)
                )
                if "SELECT" in rendered.upper():
                    # Check it has no FormattedValue parts (i.e. no interpolation)
                    has_interp = any(
                        isinstance(v, ast.FormattedValue) for v in n.values
                    )
                    if has_interp:
                        # Allow safe placeholder construction (e.g. "(?, ?, ?)")
                        # by inspecting interpolated subexpressions: if every
                        # interpolation produces a placeholder string, allow.
                        # Conservative: report and inspect.
                        offenders.append((path.name, rendered[:80]))
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                if n.func.attr == "format" and isinstance(n.func.value, ast.Constant):
                    if isinstance(n.func.value.value, str) and "SELECT" in n.func.value.value.upper():
                        offenders.append((path.name, n.func.value.value[:80]))
    # The placeholder-construction pattern (f"... IN ({placeholders})") is
    # safe but appears here; check that any interpolated value is named
    # `placeholders` (our convention).
    real_offenders = []
    for fn, snippet in offenders:
        # Re-parse and inspect; for now just allow snippets that contain
        # "placeholders" (the f-string form used in income.py for IN-list).
        if "placeholders" in snippet:
            continue
        real_offenders.append((fn, snippet))
    assert not real_offenders, (
        "Non-parameterized SQL in tool modules:\n"
        + "\n".join(f"  {fn}: {snippet}" for fn, snippet in real_offenders)
    )
