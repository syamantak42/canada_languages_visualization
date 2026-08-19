from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from canada_census_lang.runtime_assets import (  # noqa: E402
    prepare_all_runtime_assets,
    prepare_change_assets,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Precompute runtime tables and MapLibre GeoJSON assets.")
    parser.add_argument(
        "--change-only",
        action="store_true",
        help="Rebuild only the 2016→2021 crosswalk/change tables.",
    )
    args = parser.parse_args()
    if args.change_only:
        prepare_change_assets(force_crosswalk=True)
    else:
        prepare_all_runtime_assets()
    print("Runtime assets prepared.")


if __name__ == "__main__":
    main()
