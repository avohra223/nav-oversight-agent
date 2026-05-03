"""Shared fixtures for tests/agent/.

Skips the entire suite if ANTHROPIC_API_KEY isn't set so we don't fail
hard in CI environments without the key. The Phase 2 tool tests are
unaffected (they never call the API).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def _no_api_key() -> bool:
    return not os.environ.get("ANTHROPIC_API_KEY")


@pytest.fixture(scope="session", autouse=True)
def ensure_warehouse_built_for_agent() -> None:
    """The agent talks to data/nav.duckdb via Phase 2 tools; build if missing."""
    db = ROOT / "data" / "nav.duckdb"
    if not db.exists():
        from nav_oversight.build import build  # noqa: WPS433
        build(verbose=False)
    assert db.exists()


@pytest.fixture(scope="session")
def api_key_required():
    if _no_api_key():
        pytest.skip(
            "ANTHROPIC_API_KEY not set; skipping live-API agent tests. "
            "Set the env var to enable."
        )


def pytest_collection_modifyitems(config, items):
    """Skip everything in tests/agent/ if no API key is set."""
    if not _no_api_key():
        return
    skip = pytest.mark.skip(reason="ANTHROPIC_API_KEY not set")
    for item in items:
        if "tests/agent" in str(item.fspath).replace("\\", "/"):
            item.add_marker(skip)
