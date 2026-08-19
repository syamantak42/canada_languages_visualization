from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from canada_census_lang.processing import prepare_all  # noqa: E402


def main() -> None:
    data16, data21 = prepare_all()
    print(f"2016 detailed language rows: {len(data16):,}")
    print(f"2021 detailed language rows: {len(data21):,}")
    print("Prepared Census tables written to data/processed/.")


if __name__ == "__main__":
    main()
