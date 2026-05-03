"""Smoke-test every Streamlit page using streamlit.testing.

Renders each page in a synthetic AppTest, asserts no exceptions were
raised. Catches Python errors that an HTTP 200 probe wouldn't see.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from streamlit.testing.v1 import AppTest


PAGES = [
    "ui/app.py",
    "ui/pages/1_Dashboard.py",
    "ui/pages/2_Defect_Detail.py",
    "ui/pages/3_Run_Explorer.py",
    "ui/pages/4_Configuration.py",
    "ui/pages/5_Run_Live.py",
]


def main() -> int:
    failures: list[tuple[str, str]] = []
    for path in PAGES:
        full = ROOT / path
        print(f"  rendering {path:35s}", end=" ")
        at = AppTest.from_file(str(full), default_timeout=20)
        at.run()
        if at.exception:
            errs = "; ".join(str(e) for e in at.exception)
            failures.append((path, errs))
            print(f"FAIL  {errs[:160]}")
        else:
            print("OK")
    if failures:
        print()
        print(f"{len(failures)} page(s) failed:")
        for path, err in failures:
            print(f"  - {path}")
            print(f"    {err}")
        return 1
    print()
    print(f"All {len(PAGES)} pages rendered without exceptions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
