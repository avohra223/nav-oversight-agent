"""CLI entrypoint: regenerate the synthetic NAV warehouse from scratch."""
import sys
from pathlib import Path

# Allow running without pip-installing the package.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nav_oversight.build import build  # noqa: E402

if __name__ == "__main__":
    build()
