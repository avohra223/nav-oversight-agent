"""Reset audit/agent_runs/ to the fixture set only.

Removes any non-fixture run JSON files (recorded live runs) so the UI
goes back to a known clean state. Useful between demos or before pushing
to GitHub if you want to ship a deterministic experience.

Fixture files are recognised by the prefix `fixture_`. Other files are
deleted. The fixtures_manifest.json is preserved.

Usage:
    python scripts/reset_to_fixtures.py            # dry run, prints actions
    python scripts/reset_to_fixtures.py --apply    # actually delete
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "audit" / "agent_runs"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--apply", action="store_true",
        help="Actually delete the non-fixture files. Default is dry run.",
    )
    args = p.parse_args()

    if not RUNS_DIR.exists():
        print(f"No directory at {RUNS_DIR}; nothing to do.")
        return 0

    to_delete: list[Path] = []
    fixtures_kept = 0
    for p in sorted(RUNS_DIR.glob("*.json")):
        if p.name.startswith("fixture_"):
            fixtures_kept += 1
            continue
        if p.name in ("fixtures_manifest.json", "_full_suite_scoreboard.json"):
            continue
        to_delete.append(p)

    print(f"Fixtures to keep: {fixtures_kept}")
    print(f"Recorded runs to delete: {len(to_delete)}")
    for p in to_delete:
        print(f"  {p.name}")

    if not args.apply:
        print()
        print("Dry run only. Pass --apply to actually delete.")
        return 0

    for p in to_delete:
        p.unlink()
    print(f"\nDeleted {len(to_delete)} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
