from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from canada_census_lang.config import (  # noqa: E402
    ASSET_DIR,
    CHANGE_CROSSWALK,
    CHANGE_GROUP,
    CHANGE_LANGUAGE,
    GROUP_DATA_2016,
    GROUP_DATA_2021,
    LANGUAGE_DATA_2016,
    LANGUAGE_DATA_2021,
    MAP_INDEX_2016,
    MAP_INDEX_2021,
    PROVINCE_CODE_TO_NAME,
    RANK_GROUP_2016,
    RANK_GROUP_2021,
    RANK_LANGUAGE_2016,
    RANK_LANGUAGE_2021,
)
from canada_census_lang.runtime_assets import (  # noqa: E402
    division_asset_name,
    outer_asset_name,
    province_boundaries_asset_name,
)


def main() -> None:
    required = [
        LANGUAGE_DATA_2016, LANGUAGE_DATA_2021, GROUP_DATA_2016, GROUP_DATA_2021,
        MAP_INDEX_2016, MAP_INDEX_2021,
        RANK_LANGUAGE_2016, RANK_LANGUAGE_2021, RANK_GROUP_2016, RANK_GROUP_2021,
        CHANGE_CROSSWALK, CHANGE_LANGUAGE, CHANGE_GROUP,
    ]
    for year in (2016, 2021):
        required += [
            ASSET_DIR / division_asset_name(year, "Canada"),
            ASSET_DIR / outer_asset_name(year, "Canada"),
            ASSET_DIR / province_boundaries_asset_name(year),
        ]
        for province in PROVINCE_CODE_TO_NAME.values():
            required += [
                ASSET_DIR / division_asset_name(year, province),
                ASSET_DIR / outer_asset_name(year, province),
            ]
    missing = [path for path in required if not path.exists() or path.stat().st_size == 0]
    if missing:
        print("SETUP INCOMPLETE. Missing:")
        for path in missing:
            print(f"  {path.relative_to(PROJECT_ROOT)}")
        raise SystemExit(1)
    print(f"Setup OK: verified {len(required)} runtime files/assets.")


if __name__ == "__main__":
    main()
